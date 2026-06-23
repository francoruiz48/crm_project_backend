
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