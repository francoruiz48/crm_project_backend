
from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.core.context import TENANT_ORG_ID
from app.models.security_models import Role
from app.schemas.security_schemas.role_schema import RoleDetailedResponse, RoleResponse


class RoleRepository(BaseRepository):
    model = Role
    delete_strategy = DeleteStrategy.SOFT_DELETE_ALWAYS
    schema_out = RoleResponse
    schema_out_detail = RoleDetailedResponse

    @classmethod
    def _apply_tenant_filter(cls, query, is_read_operation: bool = True):
        """
        Los roles son estrictamente por organización en ambas direcciones.
        Las orgs cliente NUNCA ven los roles plantilla de la org admin.
        """
        org_id = TENANT_ORG_ID.get()
        if org_id is not None:
            query = query.filter(cls.model.organization_id == org_id)
        return query

    @classmethod
    def set_permissions(cls, session, role_id: int, permission_ids: list):
        """
        Reemplaza por completo el set de permisos de un rol (PUT, no incremental).
        Respeta el filtro de tenant (no se puede tocar un rol de otra organización).
        Devuelve el objeto ORM del rol (con `.permissions` ya actualizado), o None
        si el rol no existe / no pertenece al tenant actual.
        """
        from app.models.security_models import Permission

        query = session.query(cls.model).filter(cls.model.id == role_id)
        query = cls._apply_tenant_filter(query, is_read_operation=False)
        role = query.first()
        if not role:
            return None

        permissions = (
            session.query(Permission).filter(Permission.id.in_(permission_ids)).all()
            if permission_ids else []
        )
        role.permissions = permissions
        session.flush()
        session.refresh(role)
        return role