from app.db.repository.base_repository import BaseRepository
from app.models.security_models import Permission
from app.schemas.security_schemas.permission_schema import PermissionResponse

class PermissionRepository(BaseRepository):
    model = Permission
    schema_out = PermissionResponse