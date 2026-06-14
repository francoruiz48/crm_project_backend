from typing import List, Optional, Any
from pydantic import BaseModel, Field, field_validator
from app.schemas.base_schema import BaseCreate, BaseDetailedResponse
from app.schemas.security_schemas.permission_schema import PermissionResponse
from app.schemas.security_schemas.role_schema import RoleResponse

class UserOrganizationResponse(BaseModel, BaseDetailedResponse):
    organization_id: int
    roles: List[RoleResponse] = []
    is_owner: bool

class UserOrganizationDetailedResponse(UserOrganizationResponse):
    permission_objects: List[PermissionResponse] = []
    is_owner: bool

class UserPublicResponse(BaseModel):
    """Schema reducido para exponer usuarios dentro de una organización.
    Solo incluye lo necesario para la UI (asignaciones, menciones, chat).
    """
    id: int
    name: str
    email: str
    active: bool

    model_config = {"from_attributes": True}


class UserBase(BaseModel):
    name: str
    email: str

class UserResponse(UserBase, BaseDetailedResponse):
    organizations_access: List[UserOrganizationResponse] = []
    is_superuser: bool
    model_config = {"from_attributes": True}

class UserDetailedResponse(UserResponse):
    organizations_access: List[UserOrganizationDetailedResponse] = []
    is_superuser: bool
    model_config = {"from_attributes": True}

class UserCreate(UserBase, BaseCreate):
    password: Optional[str] = None  # opcional para no romper seeds internos

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


