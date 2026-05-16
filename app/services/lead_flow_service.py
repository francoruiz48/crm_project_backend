from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import or_
from app.services.base_service import BaseService
from app.db.unit_of_work import UnitOfWork
from app.db.repository.lead_flow_repository import LeadFlowRepository
from app.models.lead_flow import LeadFlow
from app.core.security import UserContext
from app.core.context import TENANT_ORG_ID
from app.core.constans import SystemAuditLogAction

class LeadFlowService(BaseService):
    repository = LeadFlowRepository()

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            org_id = TENANT_ORG_ID.get()
            
            # Validación: Nombre único por organización
            if obj_in.name:
                existing = uow.session.query(LeadFlow).filter(
                    LeadFlow.name.ilike(obj_in.name),
                    LeadFlow.organization_id == org_id
                ).first()
                if existing:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST, 
                        detail=[{"field": "name", "message": f"Ya existe un flujo de leads llamado '{obj_in.name}'."}]
                    )
            
            new_obj = cls.repository.create(uow.session, obj_in, user_context=user_context)
            uow.session.flush()
            cls._log_audit(uow.session, new_obj, action=SystemAuditLogAction.CREATED, changes=obj_in.model_dump(), user_id=user_context.user.id if user_context and user_context.user else None)
            return new_obj

        return cls._execute(action="Crear Flujo de Leads", func=do_create)

    @classmethod
    def update(cls, obj_id: int, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            org_id = TENANT_ORG_ID.get()
            current_obj = uow.session.query(LeadFlow).filter_by(id=obj_id).first()
            if not current_obj:
                cls._not_found(obj_id)

            # Validación: Nombre único en update
            if obj_in.name and obj_in.name.lower() != current_obj.name.lower():
                existing = uow.session.query(LeadFlow).filter(
                    LeadFlow.name.ilike(obj_in.name),
                    LeadFlow.id != obj_id,
                    LeadFlow.organization_id == org_id
                ).first()
                if existing:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST, 
                        detail=[{"field": "name", "message": f"Ya existe un flujo de leads llamado '{obj_in.name}'."}]
                    )

            updated_obj = cls.repository.update(uow.session, obj_id, obj_in, user_context=user_context)
            uow.session.flush()
            cls._log_audit(uow.session, updated_obj, action=SystemAuditLogAction.UPDATED, changes=obj_in.model_dump(exclude_unset=True), user_id=user_context.user.id if user_context and user_context.user else None)
            return updated_obj

        return cls._execute(action="Actualizar Flujo de Leads", obj_id=obj_id, func=do_update)