from fastapi import status, HTTPException
from sqlalchemy import desc
from app.db.repository.lead_flow_repository import LeadFlowRepository
from app.services.base_service import BaseService
from app.db.repository.campaign_repository import CampaignRepository
from app.core.exceptions.exceptions import ValidationError
from app.services.base_service import BaseService
from app.db.repository.workspace_repository import WorkspaceRepository
from fastapi import status, HTTPException
from app.models.campaign import Campaign
from app.models.lead_state import LeadState
from app.models.lead_state_transition import LeadStateTransition

class CampaignService(BaseService):
    repository = CampaignRepository
    workspace_repository = WorkspaceRepository
    lead_flow_repository = LeadFlowRepository

    @classmethod
    def create(cls, obj_in, created_by=None):
        
        def do_create(uow):
            errors = []

            workspace = cls.workspace_repository.get_by_id(uow.session, obj_in.workspace_id)
            if not workspace:
                errors.append({"field": "workspace_id", "message": "El espacio de trabajo especificado no existe."})
            else:
                existing = cls.repository.get_all(
                    session=uow.session, 
                    name=obj_in.name, 
                    workspace_id=obj_in.workspace_id,
                    only_active=True
                )
                
                if existing:
                    errors.append({"field": "name", "message": f"Ya existe una campaña llamada '{obj_in.name}' en este espacio de trabajo."})
            
            lead_flow = cls.lead_flow_repository.get_by_id(uow.session, obj_in.lead_flow_id)
            if not lead_flow:
                errors.append({"field": "lead_flow_id", "message": "El flujo de leads especificado no existe."})
            elif lead_flow.organization_id != workspace.organization_id:
                errors.append({"field": "lead_flow_id", "message": "El flujo de leads no pertenece a la misma organización que el espacio de trabajo."})

            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)
            
            data = obj_in.model_dump()

            # 1. Crear la campaña base
            new_campaign = cls.repository.create(uow.session, data, created_by)

            return new_campaign

        return cls._execute(action="Crear Campaña", func=do_create)