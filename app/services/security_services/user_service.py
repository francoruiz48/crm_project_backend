from app.services.base_service import BaseService
from app.db.repository.security_repositories.user_repository import UserRepository

class UserService(BaseService):
    repository = UserRepository
