from app.db.repository.base_repository import BaseRepository
from app.models.security_models import Role, User, UserOrganization
from app.schemas.security_schemas.user_schema import UserCreate, UserDetailedResponse, UserResponse
from sqlalchemy.orm import selectinload

class UserRepository(BaseRepository):
    model = User
    schema_out = UserResponse
    schema_out_detail = UserDetailedResponse

    relationships = [
        selectinload(User.organizations_access)
        .selectinload(UserOrganization.roles)
        .selectinload(Role.permissions)
    ]

    
