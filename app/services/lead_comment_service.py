from typing import Optional
from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.core.error_messages import SUCCESS_CREATE
from app.db.repository.lead_comment_repository import LeadCommentRepository
from app.core.security import UserContext
from app.core.constans import SystemAuditLogAction
from app.models.lead import Lead

class LeadCommentService(BaseService):
    repository = LeadCommentRepository

    @classmethod
    def create(cls, obj_data, user_context: Optional[UserContext] = None):
        def do_create(uow):
            # Hallazgo #18: LeadComment no tiene organization_id propio, así que hay
            # que validar acá (no lo cubre _apply_tenant_filter) que el lead_id
            # recibido pertenezca a la organización activa antes de crear el comentario.
            if user_context is not None and not user_context.is_superuser and user_context.organization_id is not None:
                lead = uow.session.query(Lead).filter_by(
                    id=obj_data.lead_id, organization_id=user_context.organization_id
                ).first()
                if not lead:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "lead_id", "message": "El lead no existe o no pertenece a esta organización."}]
                    )

            new_obj = cls.repository.create(uow.session, obj_data, user_context=user_context)
            uow.session.flush()

            payload = cls.repository._normalize_data(obj_data)
            cls._log_audit(uow.session, new_obj, action=SystemAuditLogAction.CREATED, changes=payload, user_id=user_context.user.id if user_context else None)

            return new_obj

        return cls._execute(action="Creando", func=do_create, success_msg=SUCCESS_CREATE)
