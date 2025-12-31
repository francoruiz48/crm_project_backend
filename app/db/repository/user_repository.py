from typing import Optional
from app.db.repository.base_repository import BaseRepository
from app.models.security_models import User
from app.schemas.security_schemas import UserResponse
from sqlalchemy import or_

class UserRepository(BaseRepository):
    model = User
    schema_out = UserResponse