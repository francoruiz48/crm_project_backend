from typing import List
from pydantic import BaseModel, Field
from app.schemas.base_schema import BaseCreate, BaseDetailResponse
from app.schemas.security_schemas.permission_schema import PermissionResponse

class RoleBase(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(min_length=2, max_length=50)
    

class RoleResponse(RoleBase, BaseDetailResponse):
    organization_id: int = Field(default=None, gt=0)

class RoleDetailResponse(RoleBase, BaseDetailResponse):
    organization_id: int = Field(default=None, gt=0)
    permissions: List[PermissionResponse] = []

class RoleCreate(RoleBase, BaseCreate):
    organization_id: int = Field(gt=0)