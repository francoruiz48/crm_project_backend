from typing import Optional

from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.db.unit_of_work import UnitOfWork
from app.db.repository.lead_state_transition_repository import LeadStateTransitionRepository
from app.db.repository.lead_state_repository import LeadStateRepository
from app.schemas.lead_state_transition_schema import LeadStateTransitionBulkCreate, LeadStateTransitionCreate
from app.core.security import UserContext
from app.models.lead_state import LeadState
from app.models.lead_state_transition import LeadStateTransition
from app.core.constans import SystemAuditLogAction

class LeadStateTransitionService(BaseService):
    repository = LeadStateTransitionRepository()
    state_repository = LeadStateRepository() # Necesitamos leer los estados

    @classmethod
    def create(cls, obj_in: LeadStateTransitionCreate, user_context: Optional[UserContext] = None, **kwargs):
        errors = []
        created_by = user_context.user.id if user_context and user_context.user else None
        with UnitOfWork() as uow:
            # 1. Traer los estados de la base de datos
            from_state = cls.state_repository.get_by_id(uow.session, obj_in.from_state_id, user_context=user_context)
            to_state = cls.state_repository.get_by_id(uow.session, obj_in.to_state_id, user_context=user_context)

            # 2. Validar Existencia y Pertenencia a la campaña (Acumulando errores)
            if not from_state:
                errors.append({"field": "from_state_id", "message": "El estado de origen no existe."})
            elif from_state.lead_flow_id != obj_in.lead_flow_id:
                errors.append({"field": "from_state_id", "message": "El estado de origen no pertenece al flujo de leads enviado."})

            if not to_state:
                errors.append({"field": "to_state_id", "message": "El estado de destino no existe."})
            elif to_state.lead_flow_id != obj_in.lead_flow_id:
                errors.append({"field": "to_state_id", "message": "El estado de destino no pertenece al flujo de leads enviado."})

            # 3. Validar Duplicados (Solo si los estados anteriores son válidos para evitar cruces raros)
            if not errors:
                existing_route = cls.repository.get_all(
                    uow.session,
                    lead_flow_id=obj_in.lead_flow_id, 
                    from_state_id=obj_in.from_state_id, 
                    to_state_id=obj_in.to_state_id
                )
                if existing_route:
                    errors.append({"field": "general", "message": "Esta transición ya existe en el flujo de la campaña."})

            # 4. Explotar si hay errores
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            # 5. Guardar
            transition_data = obj_in.model_dump(exclude_unset=True)
            transition_data.update(kwargs)
            
            created_obj = cls.repository.create(uow.session, transition_data, user_context=user_context)
            uow.session.flush()

            cls._log_audit(uow.session, created_obj, action=SystemAuditLogAction.CREATED, changes=transition_data, user_id=created_by)

            return created_obj
        
    # Se utiliza para crear multiples transiciones a la vez, lo cual es útil para poblar un flujo de leads nuevo sin tener que hacer múltiples requests desde el front
    @classmethod
    def create_bulk(cls, obj_in: LeadStateTransitionBulkCreate, user_context: Optional[UserContext] = None, **kwargs):
        errors = []
        created_transitions = []
        
        with UnitOfWork() as uow:
            # 1. Recopilar todos los IDs únicos para hacer UNA sola consulta a la DB
            state_ids = set()
            for t in obj_in.transitions:
                state_ids.add(t.from_state_id)
                state_ids.add(t.to_state_id)
            
            # Traemos los estados implicados y los mapeamos en un diccionario
            states_in_db = uow.session.query(cls.state_repository.model).filter(
                cls.state_repository.model.id.in_(state_ids)
            ).all()
            state_map = {s.id: s for s in states_in_db}

            # 2. Traer transiciones existentes para chequear duplicados
            existing_transitions = cls.repository.get_all(
                uow.session, lead_flow_id=obj_in.lead_flow_id
            )
            existing_pairs = {(et.from_state_id, et.to_state_id) for et in existing_transitions}

            # Set para evitar que el front mande duplicados dentro del mismo array
            incoming_pairs = set()

            # 3. Validar todo en memoria
            for idx, t in enumerate(obj_in.transitions):
                from_state = state_map.get(t.from_state_id)
                to_state = state_map.get(t.to_state_id)

                if not from_state:
                    errors.append({"field": f"transitions[{idx}].from_state_id", "message": f"El estado origen {t.from_state_id} no existe."})
                elif from_state.lead_flow_id != obj_in.lead_flow_id:
                    errors.append({"field": f"transitions[{idx}].from_state_id", "message": f"El estado {t.from_state_id} no pertenece al flujo de leads."})

                if not to_state:
                    errors.append({"field": f"transitions[{idx}].to_state_id", "message": f"El estado destino {t.to_state_id} no existe."})
                elif to_state.lead_flow_id != obj_in.lead_flow_id:
                    errors.append({"field": f"transitions[{idx}].to_state_id", "message": f"El estado {t.to_state_id} no pertenece al flujo de leads."})

                pair = (t.from_state_id, t.to_state_id)
                if pair in existing_pairs:
                    errors.append({"field": f"transitions[{idx}]", "message": "Esta transición ya existe en la base de datos."})
                if pair in incoming_pairs:
                    errors.append({"field": f"transitions[{idx}]", "message": "Transición duplicada en la misma petición."})
                
                incoming_pairs.add(pair)

            # 4. Si hay algún error estructural, cortamos la ejecución (el UoW hará rollback automático)
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            # 5. Insertar todo
            created_by = user_context.user.id if user_context and user_context.user else None
            for t in obj_in.transitions:
                transition_data = {
                    "lead_flow_id": obj_in.lead_flow_id,
                    "from_state_id": t.from_state_id,
                    "to_state_id": t.to_state_id
                }
                transition_data.update(kwargs)
                new_obj = cls.repository.create(uow.session, transition_data, user_context=user_context)
                uow.session.flush()
                
                cls._log_audit(uow.session, new_obj, action=SystemAuditLogAction.CREATED, changes=transition_data, user_id=created_by)
                
                created_transitions.append(new_obj)
                
        # Retornamos la lista de objetos creados
        return created_transitions
    
    @classmethod
    def update_bulk(cls, obj_in: LeadStateTransitionBulkCreate, user_context: Optional[UserContext] = None, **kwargs):
        def do_update(uow):
            errors = []
            created_by = user_context.user.id if user_context and user_context.user else None
            
            # 1. Traer todos los estados de este flujo para validación rápida
            states_in_db = uow.session.query(cls.state_repository.model).filter_by(
                lead_flow_id=obj_in.lead_flow_id
            ).all()
            state_map = {s.id: s for s in states_in_db}

            if not states_in_db:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, 
                    detail=[{"field": "lead_flow_id", "message": "El flujo de leads no existe o no tiene estados."}]
                )

            # 2. Validar estructura del Payload y armar el nuevo grafo (Set de tuplas)
            incoming_pairs = set()
            for idx, t in enumerate(obj_in.transitions):
                from_state = state_map.get(t.from_state_id)
                to_state = state_map.get(t.to_state_id)

                if not from_state:
                    errors.append({"field": f"transitions[{idx}].from_state_id", "message": f"El estado origen {t.from_state_id} no pertenece al flujo."})
                if not to_state:
                    errors.append({"field": f"transitions[{idx}].to_state_id", "message": f"El estado destino {t.to_state_id} no pertenece al flujo."})
                
                pair = (t.from_state_id, t.to_state_id)
                if pair in incoming_pairs:
                    errors.append({"field": f"transitions[{idx}]", "message": "Transición duplicada en la petición."})
                
                incoming_pairs.add(pair)

            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            # 3. REGLA 6: Validar "Callejones sin salida" en el NUEVO grafo
            open_states = [s for s in states_in_db if s.category == "OPEN"]
            for state in open_states:
                exits = sum(1 for pair in incoming_pairs if pair[0] == state.id)
                if exits == 0:
                    errors.append({
                        "field": "general", 
                        "message": f"El diseño es inválido. El estado '{state.name}' quedaría como un callejón sin salida (sin rutas de avance)."
                    })
            
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            # 4. FIX: Traer transiciones mediante SQLAlchemy puro para poder borrarlas luego
            from app.models.lead_state_transition import LeadStateTransition
            existing_transitions = uow.session.query(LeadStateTransition).filter_by(
                lead_flow_id=obj_in.lead_flow_id
            ).all()
            existing_map = {(et.from_state_id, et.to_state_id): et for et in existing_transitions}

            to_delete = []
            to_create = []

            # 5. Calcular el DIFF (Diferencias)
            for pair, et in existing_map.items():
                if pair not in incoming_pairs:
                    to_delete.append(et) # Estaba en DB pero no en el Payload -> Borrar
            
            for pair in incoming_pairs:
                if pair not in existing_map:
                    to_create.append(pair) # Está en Payload pero no en DB -> Crear

            # 6. Ejecutar Eliminaciones
            for et in to_delete:
                uow.session.delete(et) # Ahora sí funciona porque et es un objeto SQLAlchemy
                cls._log_audit(uow.session, et, action=SystemAuditLogAction.DELETED, changes=None, user_id=created_by)

            # 7. Ejecutar Creaciones
            for pair in to_create:
                transition_data = {
                    "lead_flow_id": obj_in.lead_flow_id,
                    "from_state_id": pair[0],
                    "to_state_id": pair[1]
                }
                transition_data.update(kwargs)
                new_obj = cls.repository.create(uow.session, transition_data, user_context=user_context)
                
                cls._log_audit(uow.session, new_obj, action=SystemAuditLogAction.CREATED, changes=transition_data, user_id=created_by)

            uow.session.flush()

            # 8. FIX: Retornar con detailed=True para que coincida con el schema_out_detail del controlador
            return cls.repository.get_all(uow.session, lead_flow_id=obj_in.lead_flow_id, detailed=True)

        # Envolvemos todo en el execute para manejo seguro de transacciones
        return cls._execute(action="Sincronizar Transiciones Masivas", func=do_update)
    

    @classmethod
    def delete(cls, obj_id: int, user_context: Optional[UserContext] = None, force: bool = False):
        def do_delete(uow):

            transition = uow.session.query(LeadStateTransition).filter_by(id=obj_id).first()
            if not transition:
                cls._not_found(obj_id)

            from_state_id = transition.from_state_id

            # Eliminamos la transición
            result = cls.repository.delete(uow.session, obj_id, user_context=user_context)
            uow.session.flush()

            # Regla 6: Validar si acabamos de dejar al estado origen como un "callejón sin salida"
            origin_state = uow.session.query(LeadState).filter_by(id=from_state_id).first()
            
            # Solo nos preocupan los estados OPEN. Si es WON/LOST, es normal que no tengan salidas.
            if origin_state and origin_state.category == "OPEN":
                remaining_exits = uow.session.query(LeadStateTransition).filter_by(from_state_id=from_state_id).count()
                
                if remaining_exits == 0:
                    # Es un callejón sin salida. Hacemos Rollback y lanzamos error.
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "general", "message": f"No se puede eliminar esta transición. El estado '{origin_state.name}' quedaría sin ninguna ruta de salida."}]
                    )

            cls._log_audit(uow.session, transition, action=SystemAuditLogAction.DELETED, changes=None, user_id=user_context.user.id if user_context and user_context.user else None)
            return result

        return cls._execute(action="Eliminar Transición", obj_id=obj_id, func=do_delete)