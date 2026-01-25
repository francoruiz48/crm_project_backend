from app.services.base_service import BaseService
from app.db.repository.campaign_repository import CampaignRepository
from app.core.exceptions.exceptions import ValidationError
from app.services.base_service import BaseService
from app.db.repository.workspace_repository import WorkspaceRepository

class CampaignService(BaseService):
    repository = CampaignRepository
    workspace_repository = WorkspaceRepository

    @classmethod
    def create(cls, obj_in, created_by=None):
        def do_create(uow):
            existing = cls.repository.get_all(
                session=uow.session, 
                name=obj_in.name, 
                workspace_id=obj_in.workspace_id,
                only_active=True
            )
            
            if existing:
                raise ValidationError(f"Ya existe una campaña llamada '{obj_in.name}' en este espacio de trabajo.", field="name")
            
            #Inferencia de organization
            workspace = cls.workspace_repository.get_by_id(uow.session, obj_in.workspace_id)
            if not workspace:
                raise ValidationError("El espacio de trabajo especificado no existe.", field="workspace_id")
            
            data = obj_in.model_dump()
            data['organization_id'] = workspace.organization_id

            return cls.repository.create(uow.session, data, created_by)

        return cls._execute(action="Crear Campaña", func=do_create)