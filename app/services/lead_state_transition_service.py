from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.db.unit_of_work import UnitOfWork
from app.db.repository.lead_state_transition_repository import LeadStateTransitionRepository
from app.db.repository.lead_state_repository import LeadStateRepository
from app.schemas.lead_state_transition_schema import LeadStateTransitionBulkCreate, LeadStateTransitionCreate

class LeadStateTransitionService(BaseService):
    repository = LeadStateTransitionRepository()
    state_repository = LeadStateRepository() # Necesitamos leer los estados

    @classmethod
    def create(cls, obj_in: LeadStateTransitionCreate, **kwargs):
        errors = []
        
        with UnitOfWork() as uow:
            # 1. Traer los estados de la base de datos
            from_state = cls.state_repository.get_by_id(uow.session, obj_in.from_state_id)
            to_state = cls.state_repository.get_by_id(uow.session, obj_in.to_state_id)

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
            
            created_obj = cls.repository.create(uow.session, transition_data)
            return created_obj
        
    # Se utiliza para crear multiples transiciones a la vez, lo cual es útil para poblar un flujo de leads nuevo sin tener que hacer múltiples requests desde el front
    @classmethod
    def create_bulk(cls, obj_in: LeadStateTransitionBulkCreate, **kwargs):
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
            for t in obj_in.transitions:
                transition_data = {
                    "lead_flow_id": obj_in.lead_flow_id,
                    "from_state_id": t.from_state_id,
                    "to_state_id": t.to_state_id
                }
                transition_data.update(kwargs)
                new_obj = cls.repository.create(uow.session, transition_data)
                created_transitions.append(new_obj)
                
        # Retornamos la lista de objetos creados
        return created_transitions