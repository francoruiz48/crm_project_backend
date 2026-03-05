from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.db.unit_of_work import UnitOfWork
from app.db.repository.lead_state_repository import LeadStateRepository
from app.schemas.lead_state_schema import LeadStateCreate

class LeadStateService(BaseService):
    repository = LeadStateRepository()

    @classmethod
    def create(cls, obj_in: LeadStateCreate, **kwargs):
        errors = []
        
        with UnitOfWork() as uow:
            # Regla: Solo puede haber un estado inicial por campaña
            if obj_in.is_initial:
                # Asumiendo que tu base repository tiene un get_by o find_first
                existing_initial = cls.repository.get_all(
                    uow.session, 
                    campaign_id=obj_in.campaign_id, 
                    is_initial=True
                )
                if existing_initial:
                    errors.append({
                        "field": "is_initial", 
                        "message": "Ya existe un estado inicial para esta campaña. Desmárquelo antes de crear uno nuevo."
                    })

            # Si hay errores de negocio, explotamos aquí devolviendo el array
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            # Preparar datos usando Pydantic v2
            state_data = obj_in.model_dump(exclude_unset=True)
            state_data.update(kwargs) # Inyectamos organization_id aquí si viene del controller
            
            created_obj = cls.repository.create(uow.session, state_data)
            return created_obj

    @classmethod
    def update(cls, obj_id: int, obj_in):
        errors = []
        
        with UnitOfWork() as uow:
            current_state = cls.repository.get_by_id(uow.session, obj_id)
            if not current_state:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Estado no encontrado")

            update_data = obj_in.model_dump(exclude_unset=True)

            # Si está intentando volverlo inicial y antes no lo era
            if update_data.get("is_initial") and not current_state.is_initial:
                existing_initial = cls.repository.get_all(
                    uow.session, 
                    campaign_id=current_state.campaign_id, 
                    is_initial=True
                )
                if existing_initial and existing_initial.id != obj_id:
                    errors.append({
                        "field": "is_initial", 
                        "message": "Ya existe un estado inicial para esta campaña."
                    })

            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            cls.repository.update(uow.session, obj_id, update_data)
            return cls.repository.get_by_id(uow.session, obj_id)