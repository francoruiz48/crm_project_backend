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

class UserBase(BaseModel):
    name: str
    email: str

class UserResponse(UserBase, BaseDetailedResponse):
    organizations_access: List[UserOrganizationResponse] = []
    is_superuser: bool

class UserDetailedResponse(UserResponse):
    organizations_access: List[UserOrganizationDetailedResponse] = []
    is_superuser: bool

class UserCreate(UserBase, BaseCreate):
    pass

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


