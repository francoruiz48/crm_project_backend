
from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.security_models import Role
from app.schemas.security_schemas.role_schema import RoleDetailedResponse, RoleResponse


class RoleRepository(BaseRepository):
    model = Role
    delete_strategy = DeleteStrategy.SOFT_DELETE_ALWAYS
    schema_out = RoleResponse
    schema_out_detail = RoleDetailedResponse