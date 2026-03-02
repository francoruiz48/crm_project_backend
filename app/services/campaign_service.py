
from app.services.base_service import BaseService
from app.db.repository.campaign_repository import CampaignRepository
from app.core.exceptions.exceptions import ValidationError
from app.services.base_service import BaseService
from app.db.repository.workspace_repository import WorkspaceRepository
from fastapi import status, HTTPException

class CampaignService(BaseService):
    repository = CampaignRepository
    workspace_repository = WorkspaceRepository

    @classmethod
    def create(cls, obj_in, created_by=None):
        
        def do_create(uow):
            errors = []

            #Inferencia de organization
            workspace = cls.workspace_repository.get_by_id(uow.session, obj_in.workspace_id)
            if not workspace:
                errors.append({"field": "workspace_id", "message": "El espacio de trabajo especificado no existe."})
            else:
                existing = cls.repository.get_all(
                    session=uow.session, 
                    name=obj_in.name, 
                    workspace_id=obj_in.workspace_id,
                    organizacion_id=workspace.organization_id,
                    only_active=True
                )
                
                if existing:
                    errors.append({"field": "name", "message": f"Ya existe una campaña llamada '{obj_in.name}' en este espacio de trabajo."})
            

            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)
            
            data = obj_in.model_dump()
            data['organization_id'] = workspace.organization_id


            return cls.repository.create(uow.session, data, created_by)

        return cls._execute(action="Crear Campaña", func=do_create)