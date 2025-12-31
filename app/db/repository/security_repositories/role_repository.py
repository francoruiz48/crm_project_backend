
from app.db.repository.base_repository import BaseRepository
from app.models.security_models import Role
from app.schemas.security_schemas.role_schema import RoleDetailResponse, RoleResponse


class RoleRepository(BaseRepository):
    model = Role
    schema_out = RoleResponse
    schema_out_detail = RoleDetailResponse