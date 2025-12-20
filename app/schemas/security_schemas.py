from typing import Optional, List
from pydantic import BaseModel

class PermissionBase(BaseModel):
    name: str
    codename: str

class RoleBase(BaseModel):
    name: str
    code: str
    permissions: List[PermissionBase] = []

class UserResponse(BaseModel):
    id: int
    email: str
    active: bool = True
    role: Optional[RoleBase] = None

    class Config:
        from_attributes = True