from typing import List, Optional, Any
from pydantic import BaseModel, Field, field_validator
from app.schemas.base_schema import BaseCreate, BaseDetailResponse
from app.schemas.security_schemas.permission_schema import PermissionResponse
from app.schemas.security_schemas.role_schema import RoleDetailResponse, RoleResponse

class UserOrganizationResponse(BaseModel, BaseDetailResponse):
    organization_id: int
    roles: List[RoleResponse] = [] 

class UserOrganizationDetailResponse(UserOrganizationResponse):
    permission_objects: List[PermissionResponse] = []

class UserBase(BaseModel):
    email: str

class UserResponse(UserBase, BaseDetailResponse):
    organizations_access: List[UserOrganizationResponse] = []
    is_superuser: bool

class UserDetailResponse(UserResponse):
    organizations_access: List[UserOrganizationDetailResponse] = []

class UserCreate(UserBase, BaseCreate):
    pass


