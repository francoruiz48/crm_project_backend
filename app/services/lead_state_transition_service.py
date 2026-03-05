from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.db.unit_of_work import UnitOfWork
from app.db.repository.lead_state_transition_repository import LeadStateTransitionRepository
from app.db.repository.lead_state_repository import LeadStateRepository
from app.schemas.lead_state_transition_schema import LeadStateTransitionCreate

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
            elif from_state.campaign_id != obj_in.campaign_id:
                errors.append({"field": "from_state_id", "message": "El estado de origen no pertenece a la campaña enviada."})

            if not to_state:
                errors.append({"field": "to_state_id", "message": "El estado de destino no existe."})
            elif to_state.campaign_id != obj_in.campaign_id:
                errors.append({"field": "to_state_id", "message": "El estado de destino no pertenece a la campaña enviada."})

            # 3. Validar Duplicados (Solo si los estados anteriores son válidos para evitar cruces raros)
            if not errors:
                existing_route = cls.repository.get_all(
                    uow.session,
                    campaign_id=obj_in.campaign_id, 
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