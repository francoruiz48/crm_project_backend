from app.db.repository.base_repository import BaseRepository
from app.models.security_models import Role, User
from app.schemas.security_schemas.user_schema import UserCreate, UserDetailResponse, UserResponse
from sqlalchemy.orm import selectinload

class UserRepository(BaseRepository):
    model = User
    schema_out = UserResponse
    schema_out_detail = UserDetailResponse

    relationships = [
        selectinload(User.roles).selectinload(Role.permissions)
    ]
