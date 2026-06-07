from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import func
from app.services.base_service import BaseService
from app.db.unit_of_work import UnitOfWork
from app.db.repository.lead_state_repository import LeadStateRepository
from app.schemas.lead_state_schema import LeadStateCreate
from app.core.security import UserContext
from app.models.lead_state import LeadState
from app.models.lead_state_transition import LeadStateTransition
from app.schemas.lead_state_schema import LeadStateResponse
from app.core.constans import SystemAuditLogAction

class LeadStateService(BaseService):
    repository = LeadStateRepository()

    @classmethod
    def _handle_order_logic(cls, session, lead_flow_id: int, category: str, provided_order: int = None, current_state_id: int = None, errors: list = None):
        """
        Calcula o valida el 'order' para los estados.
        Solo los estados OPEN tienen orden.
        """
        # 1. Si no es OPEN, no tiene orden.
        if category != "OPEN":
            return None
        
        # 2. Si el usuario envió un orden manual, verificamos que no esté repetido
        if provided_order is not None:
            query = session.query(cls.repository.model).filter_by(
                lead_flow_id=lead_flow_id,
                category="OPEN",
                order=provided_order
            )
            
            # Si es un UPDATE, excluimos el estado actual de la búsqueda
            if current_state_id:
                query = query.filter(cls.repository.model.id != current_state_id)
            
            if query.first():
                errors.append({"field": "order", "message": f"El orden {provided_order} ya está en uso por otro estado de esta campaña."})
            
            return provided_order
            
        # 3. Si el usuario NO envió orden, autocalculamos el último + 1
        else:
            max_order = session.query(func.max(cls.repository.model.order)).filter_by(
                lead_flow_id=lead_flow_id,
                category="OPEN"
            ).scalar()
            
            return (max_order or 0) + 1


    @classmethod
    def create(cls, obj_in: LeadStateCreate, user_context: Optional[UserContext] = None, **kwargs):
        errors = []
        created_by = user_context.user.id if user_context and user_context.user else None

        with UnitOfWork() as uow:
            # Regla 1: Un solo estado inicial
            if obj_in.is_initial:
                existing_initial = cls.repository.get_all(
                    uow.session, 
                    lead_flow_id=obj_in.lead_flow_id, 
                    is_initial=True
                )
                if existing_initial:
                    errors.append({
                        "field": "is_initial", 
                        "message": "Ya existe un estado inicial para esta campaña. Desmárquelo antes de crear uno nuevo."
                    })

            # Regla 2: Autocalcular o Validar el Order
            calculated_order = cls._handle_order_logic(
                session=uow.session, 
                lead_flow_id=obj_in.lead_flow_id,
                category=obj_in.category,
                provided_order=obj_in.order,
                errors=errors
            )

            # Si hay errores de negocio, explotamos aquí devolviendo el array
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            # Preparar datos
            state_data = obj_in.model_dump(exclude_unset=True)
            state_data.update(kwargs) 
            
            # Forzamos el order calculado
            state_data["order"] = calculated_order 
            
            created_obj = cls.repository.create(uow.session, state_data, user_context=user_context)
            uow.session.flush()

            # LOG DE AUDITORÍA
            cls._log_audit(uow.session, created_obj, action=SystemAuditLogAction.CREATED, changes=state_data, user_id=created_by)

            return created_obj

    @classmethod
    def get_allowed_next_states(cls, current_state_id: int, user_context: Optional[UserContext] = None):
        """
        Devuelve una lista de los estados a los que un lead puede transicionar,
        basado en las rutas definidas en el LeadFlowGraph.
        """
        def do_get(uow):
            
            # 1. Validar que el estado actual exista y pertenezca a la organización
            current_state = cls.repository.get_by_id(uow.session, current_state_id, user_context=user_context)
            if not current_state:
                cls._not_found(current_state_id)

            # 2. Consultar los estados destino permitidos
            next_states = uow.session.query(LeadState).join(
                LeadStateTransition, LeadState.id == LeadStateTransition.to_state_id
            ).filter(
                LeadStateTransition.from_state_id == current_state_id
            ).order_by(
                LeadState.order.asc() # Ordenamos para que en el front el dropdown quede prolijo
            ).all()

            return [LeadStateResponse.model_validate(state) for state in next_states]

        return cls._execute(
            action="Obtener siguientes estados permitidos", 
            obj_id=current_state_id, 
            func=do_get
        )

    @classmethod
    def update(cls, obj_id: int, obj_in, user_context: Optional[UserContext] = None):
        errors = []
        updated_by = user_context.user.id if user_context and user_context.user else None

        with UnitOfWork() as uow:
            current_state = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not current_state:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Estado no encontrado")

            update_data = obj_in.model_dump(exclude_unset=True)
            
            new_category = update_data.get("category", current_state.category)
            new_order = update_data.get("order")
            
            # --- EVALUAR ORDEN Y CATEGORÍA ---
            # Si el usuario mandó order, o cambió la categoría, reevaluamos
            if "order" in update_data or "category" in update_data:
                
                # Caso especial: Sigue siendo OPEN pero no mandaron el 'order' en el payload.
                # En un PUT parcial o full, si no mandan 'order' pero era OPEN, le respetamos el viejo.
                if new_category == "OPEN" and "order" not in update_data:
                    if current_state.category == "OPEN":
                        calculated_order = current_state.order
                    else:
                        # Pasó de WON/LOST a OPEN. Hay que calcularle un orden al final.
                        calculated_order = cls._handle_order_logic(
                            session=uow.session, 
                            lead_flow_id=current_state.lead_flow_id, 
                            category=new_category, 
                            current_state_id=obj_id, 
                            errors=errors
                        )
                else:
                    # Flujo normal de validación de nuevo orden o forzado a NULL por no ser OPEN
                    calculated_order = cls._handle_order_logic(
                        session=uow.session, 
                        lead_flow_id=current_state.lead_flow_id,
                        category=new_category,
                        provided_order=new_order,
                        current_state_id=obj_id,
                        errors=errors
                    )
                
                update_data["order"] = calculated_order

            # --- EVALUAR ESTADO INICIAL ---
            if update_data.get("is_initial") and not current_state.is_initial:
                existing_initial = cls.repository.get_all(
                    uow.session, 
                    lead_flow_id=current_state.lead_flow_id, 
                    is_initial=True
                )
                if existing_initial and existing_initial[0].id != obj_id:
                    errors.append({
                        "field": "is_initial", 
                        "message": "Ya existe un estado inicial para esta campaña."
                    })

            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            # ARMAMOS EL DIFF DE AUDITORÍA
            changes = {}
            for key, new_val in update_data.items():
                if hasattr(current_state, key):
                    old_val = getattr(current_state, key)
                    if old_val != new_val:
                        changes[key] = {"old": old_val, "new": new_val}

            cls.repository.update(uow.session, obj_id, update_data, user_context=user_context)
            uow.session.flush()
            updated_state = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)

            if changes:
                cls._log_audit(uow.session, updated_state, action=SystemAuditLogAction.UPDATED, changes=changes, user_id=updated_by)

            return updated_state
        

    @classmethod
    def delete(cls, obj_id: int, user_context: Optional[UserContext] = None):
        def do_delete(uow):
            from app.models.lead_state import LeadState
            
            state_to_delete = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not state_to_delete:
                cls._not_found(obj_id)

            # Regla 4: Bloquear eliminación de estado inicial
            if state_to_delete.is_initial:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "general", "message": "No se puede eliminar un estado inicial."}]
                )

            flow_id = state_to_delete.lead_flow_id
            category = state_to_delete.category
            deleted_order = state_to_delete.order

            # Eliminamos el estado
            result = cls.repository.delete(uow.session, obj_id, user_context=user_context)
            uow.session.flush()

            # Regla 5: Reordenar los estados OPEN restantes
            if category == "OPEN" and deleted_order is not None:
                states_to_reorder = uow.session.query(LeadState).filter(
                    LeadState.lead_flow_id == flow_id,
                    LeadState.category == "OPEN",
                    LeadState.order > deleted_order
                ).order_by(LeadState.order.asc()).all()

                for state in states_to_reorder:
                    state.order -= 1
                    uow.session.add(state)
                
                uow.session.flush()

            cls._log_audit(uow.session, state_to_delete, action=SystemAuditLogAction.DELETED, changes=None, user_id=user_context.user.id if user_context and user_context.user else None)
            return result

        return cls._execute(action="Eliminar Estado de Lead", obj_id=obj_id, func=do_delete)