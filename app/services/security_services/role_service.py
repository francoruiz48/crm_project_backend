from app.services.base_service import BaseService
from app.db.repository.security_repositories.role_repository import RoleRepository

class RoleService(BaseService):
    repository = RoleRepository
