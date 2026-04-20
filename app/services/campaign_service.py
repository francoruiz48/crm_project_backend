from typing import Optional
from fastapi import status, HTTPException
from app.db.repository.lead_flow_repository import LeadFlowRepository
from app.models.lead_flow import LeadFlow
from app.services.base_service import BaseService
from app.db.repository.campaign_repository import CampaignRepository
from app.services.base_service import BaseService
from app.db.repository.workspace_repository import WorkspaceRepository
from fastapi import status, HTTPException
from app.core.security import UserContext
from app.models.lead import Lead

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
    
    @classmethod
    def update(cls, obj_id: int, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            campaign = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not campaign:
                cls._not_found(obj_id)

            errors = []

            # Validación Crítica: No cambiar lead_flow_id si ya tiene leads
            if obj_in.lead_flow_id and obj_in.lead_flow_id != campaign.lead_flow_id:
                
                leads_count = uow.session.query(Lead).filter_by(campaign_id=obj_id).count()
                
                if leads_count > 0:
                    errors.append({
                        "field": "lead_flow_id", 
                        "message": "No se puede cambiar el flujo de leads porque esta campaña ya tiene prospectos asignados. Cree una nueva campaña."
                    })
                else:
                    # Si no tiene leads, validamos que el nuevo flujo exista en la misma org
                    lead_flow = cls.lead_flow_repository.get_by_id(uow.session, obj_in.lead_flow_id, user_context=user_context)
                    if not lead_flow or lead_flow.organization_id != campaign.organization_id:
                        errors.append({"field": "lead_flow_id", "message": "El flujo de leads especificado no es válido o no pertenece a esta organización."})

            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            updated_campaign = cls.repository.update(uow.session, obj_id, obj_in, user_context=user_context)
            uow.session.flush()
            
            cls._log_audit(
                session=uow.session,
                obj=updated_campaign,
                action="UPDATE",
                changes=obj_in.model_dump(exclude_unset=True),
                user_id=user_context.user.id if user_context and user_context.user else None
            )

            return updated_campaign

        return cls._execute(action="Actualizar Campaña", obj_id=obj_id, func=do_update)
