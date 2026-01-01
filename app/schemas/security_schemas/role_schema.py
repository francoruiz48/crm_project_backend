from typing import List
from pydantic import BaseModel
from app.schemas.base_schema import BaseCreate, BaseDetailResponse
from app.schemas.security_schemas.permission_schema import PermissionResponse

class RoleBase(BaseModel):
    name: str
    code: str

class RoleResponse(RoleBase, BaseDetailResponse):
    pass

class RoleDetailResponse(RoleBase, BaseDetailResponse):
    permissions: List[PermissionResponse] = []

class RoleCreate(RoleBase, BaseCreate):
    pass