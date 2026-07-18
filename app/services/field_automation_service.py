from typing import Optional
from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.core.error_messages import SUCCESS_CREATE
from app.db.repository.field_automation_repository import FieldAutomationRepository
from app.core.security import UserContext
from app.core.constans import SystemAuditLogAction
from app.models.campaign import Campaign

class FieldAutomationService(BaseService):
    repository = FieldAutomationRepository

    @classmethod
    def create(cls, obj_data, user_context: Optional[UserContext] = None):
        def do_create(uow):
            # Hallazgo #20: FieldAutomation no tiene organization_id propio, así que hay
            # que validar acá que el campaign_id recibido pertenezca a la organización activa.
            if user_context is not None and not user_context.is_superuser and user_context.organization_id is not None:
                campaign = uow.session.query(Campaign).filter_by(
                    id=obj_data.campaign_id, organization_id=user_context.organization_id
                ).first()
                if not campaign:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "campaign_id", "message": "La campaña no existe o no pertenece a esta organización."}]
                    )

            new_obj = cls.repository.create(uow.session, obj_data, user_context=user_context)
            uow.session.flush()

            payload = cls.repository._normalize_data(obj_data)
            cls._log_audit(uow.session, new_obj, action=SystemAuditLogAction.CREATED, changes=payload, user_id=user_context.user.id if user_context else None)

            return new_obj

        return cls._execute(action="Creando", func=do_create, success_msg=SUCCESS_CREATE)
