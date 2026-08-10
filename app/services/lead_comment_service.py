from typing import Optional
from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.core.error_messages import SUCCESS_CREATE
from app.db.repository.lead_comment_repository import LeadCommentRepository
from app.db.unit_of_work import UnitOfWork
from app.core.security import UserContext
from app.core.constans import SystemAuditLogAction
from app.db.repository.lead_repository import LeadRepository
from app.models.lead import Lead

class LeadCommentService(BaseService):
    repository = LeadCommentRepository

    @classmethod
    def create(cls, obj_data, user_context: Optional[UserContext] = None):
        def do_create(uow):
            # obj_data.lead_id llega como public_uuid (Fase 3, ver backend/AGENTS.md §18); se
            # resuelve acá porque la query de abajo es cruda.
            # Hallazgo #18: LeadComment no tiene organization_id propio, así que hay
            # que validar acá (no lo cubre _apply_tenant_filter) que el lead_id
            # recibido pertenezca a la organización activa antes de crear el comentario.
            if user_context is not None and not user_context.is_superuser and user_context.organization_id is not None:
                lead_internal_id = LeadRepository.get_internal_id_by_public_uuid(uow.session, obj_data.lead_id)
                lead = uow.session.query(Lead).filter_by(
                    id=lead_internal_id, organization_id=user_context.organization_id
                ).first() if lead_internal_id is not None else None
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

    @classmethod
    def _assert_can_modify_comment(cls, comment, user_context: Optional[UserContext] = None, action_label: str = "editar"):
        """SEGURIDAD: mismo patrón que CampaignService._assert_can_modify_campaign — solo el
        autor del comentario, el owner de la organización o un superadmin pueden editar/eliminar
        un comentario ajeno, aunque el usuario tenga el permiso RBAC genérico
        (lead_comment:update/delete) vía su rol. Pedido explícito del usuario tras notar que,
        tal como estaba, cualquiera con ese permiso por rol podía tocar comentarios de otra
        persona (mismo hallazgo que ya se había documentado y dejado pendiente antes)."""
        if user_context and user_context.user:
            is_superuser = getattr(user_context, 'is_superuser', False)
            is_owner = getattr(user_context, 'is_owner', False)
            # `comment` viene de repository.get_by_id(), que siempre devuelve el schema Detailed
            # (bug de BaseRepository.get_by_id catalogado en backend/AGENTS.md §18-bis -- mismo
            # hallazgo que en LeadView/Campaign). No tiene `created_by` (se sacó de
            # BaseDetailedResponse a favor de creator/updater), así que se compara contra el
            # nested `creator` (uuid real) en vez del id interno viejo.
            is_creator = comment.creator is not None and comment.creator.id == user_context.user.public_uuid
            if not (is_superuser or is_owner or is_creator):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail=f"No tenés permiso para {action_label} este comentario."
                )

    @classmethod
    def update(cls, obj_id: str, obj_data, user_context: Optional[UserContext] = None):
        with UnitOfWork() as uow:
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)
            # detailed=True explícito: _assert_can_modify_comment lee comment.creator,
            # que solo existe en schema_out_detail (ver fix de get_by_id en
            # base_repository.py, backend/AGENTS.md §18-ter).
            comment = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context, detailed=True)
            if not comment:
                cls._not_found(obj_id)
            cls._assert_can_modify_comment(comment, user_context, action_label="editar")
        return super().update(obj_id, obj_data, user_context=user_context)

    @classmethod
    def delete(cls, obj_id: str, user_context: Optional[UserContext] = None, force: bool = False):
        with UnitOfWork() as uow:
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)
            # detailed=True explícito: _assert_can_modify_comment lee comment.creator,
            # que solo existe en schema_out_detail (ver fix de get_by_id en
            # base_repository.py, backend/AGENTS.md §18-ter).
            comment = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context, detailed=True)
            if not comment:
                cls._not_found(obj_id)
            cls._assert_can_modify_comment(comment, user_context, action_label="eliminar")
        return super().delete(obj_id, user_context=user_context, force=force)
