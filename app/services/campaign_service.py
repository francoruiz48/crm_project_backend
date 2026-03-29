from typing import Optional

from fastapi import status, HTTPException
from sqlalchemy import desc
from app.core.constans import DEFAULT_PAGE_SIZE
from app.db.repository.lead_flow_repository import LeadFlowRepository
from app.models.lead_flow import LeadFlow
from app.services.base_service import BaseService
from app.db.repository.campaign_repository import CampaignRepository
from app.core.exceptions.exceptions import ValidationError
from app.services.base_service import BaseService
from app.db.repository.workspace_repository import WorkspaceRepository
from fastapi import status, HTTPException
from app.models.campaign import Campaign
from app.models.lead_state import LeadState
from app.models.lead_state_transition import LeadStateTransition
from app.core.security import UserContext

class CampaignService(BaseService):
    repository = CampaignRepository
    workspace_repository = WorkspaceRepository
    lead_flow_repository = LeadFlowRepository

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        
        def do_create(uow):
            errors = []

            workspace = cls.workspace_repository.get_by_id(uow.session, obj_in.workspace_id, user_context=user_context)
            if not workspace:
                errors.append({"field": "workspace_id", "message": "El espacio de trabajo especificado no existe."})
            else:
                existing = cls.repository.get_all(
                    session=uow.session,
                    name=obj_in.name,
                    workspace_id=obj_in.workspace_id,
                    only_active=True,
                    user_context=user_context
                )
                
                if existing:
                    errors.append({"field": "name", "message": f"Ya existe una campaña llamada '{obj_in.name}' en este espacio de trabajo."})
            
            
            target_lead_flow_id = obj_in.lead_flow_id
            
            if not target_lead_flow_id:
                # Si no envía ID, buscamos el flujo predeterminado (el más antiguo de la org)
                default_flow = uow.session.query(LeadFlow).filter_by(
                    organization_id=workspace.organization_id
                ).order_by(LeadFlow.created_at.asc()).first()
                
                if not default_flow:
                    errors.append({"field": "lead_flow_id", "message": "La organización no tiene flujos de leads. Especifique uno manualmente."})
                else:
                    target_lead_flow_id = default_flow.id
            else:
                # Si envía ID, validamos que exista y pertenezca a su org
                lead_flow = cls.lead_flow_repository.get_by_id(uow.session, target_lead_flow_id, user_context=user_context)
                if not lead_flow:
                    errors.append({"field": "lead_flow_id", "message": "El flujo de leads especificado no existe."})
                elif lead_flow.organization_id != workspace.organization_id:
                    errors.append({"field": "lead_flow_id", "message": "El flujo de leads no pertenece a la misma organización."})

            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)
            
            data = obj_in.model_dump(exclude={"lead_flow_id"}) 
            data["lead_flow_id"] = target_lead_flow_id

            # 1. Crear la campaña base
            new_campaign = cls.repository.create(uow.session, data, user_context=user_context)
            
            # 2. Flush para que la BD le asigne un ID a new_campaign (necesario para el log)
            uow.session.flush() 

            # 3. LOG DE AUDITORÍA (Llamamos al helper del BaseService)
            cls._log_audit(
                session=uow.session,
                obj=new_campaign,
                action="CREATE",
                changes=data,
                user_id=user_context.user.id
            )

            return new_campaign

        return cls._execute(action="Crear Campaña", func=do_create)
    
