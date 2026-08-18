from typing import Optional
from app.services.base_service import BaseService
from app.db.repository.security_repositories.role_repository import RoleRepository
from app.db.repository.security_repositories.permission_repository import PermissionRepository
from app.core.security import UserContext
from app.core.constans import SystemAuditLogAction
from app.core.error_messages import SUCCESS_UPDATE
from app.core.exceptions.exceptions import AppException

class RoleService(BaseService):
    repository = RoleRepository

    @classmethod
    def set_permissions(cls, role_id: str, permission_ids: list[str], user_context: Optional[UserContext] = None):
        """
        Reemplaza por completo el set de permisos de un rol (PUT, no incremental).
        `role_id` y cada entrada de `permission_ids` llegan como public_uuid (lo único
        que conoce el front); acá se resuelven a los ids internos antes de tocar el repo.
        """
        def do_set(uow):
            internal_role_id = cls._resolve_id(uow.session, role_id)
            if internal_role_id is None:
                cls._not_found(role_id)

            old_role = cls.repository.get_by_id(uow.session, internal_role_id, user_context, detailed=True)
            if not old_role:
                cls._not_found(role_id)
            old_codenames = sorted(p.codename for p in old_role.permissions)

            # Los permisos son entidades globales (sin organization_id), no requieren
            # resolución por tenant -- solo traducimos uuid público -> id interno.
            uuid_to_id = PermissionRepository.get_internal_ids_by_public_uuids(uow.session, permission_ids)
            not_found = [u for u in permission_ids if u not in uuid_to_id]
            if not_found:
                raise AppException(detail=f"Permisos no encontrados: {', '.join(not_found)}")

            updated_role = cls.repository.set_permissions(uow.session, internal_role_id, list(uuid_to_id.values()))
            if not updated_role:
                cls._not_found(role_id)

            new_codenames = sorted(p.codename for p in updated_role.permissions)
            if old_codenames != new_codenames:
                cls._log_audit(
                    uow.session, updated_role,
                    action=SystemAuditLogAction.UPDATED,
                    changes={"permissions": {"old": old_codenames, "new": new_codenames}},
                    user_id=user_context.user.id if user_context else None,
                    internal_id=internal_role_id,
                )

            return cls.repository.schema_out_detail.model_validate(updated_role)

        return cls._execute(action="Actualizando permisos de rol", obj_id=role_id, func=do_set, success_msg=SUCCESS_UPDATE)
