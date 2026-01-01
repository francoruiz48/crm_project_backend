from app.services.base_service import BaseService
from app.db.repository.security_repositories.permission_repository import PermissionRepository

class PermissionService(BaseService):
    repository = PermissionRepository
