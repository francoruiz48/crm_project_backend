from datetime import date
from typing import List, Optional, Any
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.core.security import normalize_email
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
    # No hereda BaseResponse (es un schema standalone), así que el alias a
    # public_uuid se declara acá directo -- ver base_schema.py para el porqué.
    id: str = Field(validation_alias="public_uuid")
    name: str
    last_name: Optional[str] = None
    email: str
    active: bool

    model_config = {"from_attributes": True, "populate_by_name": True}


class UserBase(BaseModel):
    name: str
    last_name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None

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
    last_name: Optional[str] = None
    # Hallazgo #14: antes era `Optional[str]` (sin validar formato). EmailStr
    # rechaza formatos inválidos con 422; la unicidad se chequea aparte en
    # auth_controller.py::update_me (acá no hay acceso a la DB para hacerlo).
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None

    # Hallazgo #13: misma normalización que Login/RegisterRequest, para que
    # el cambio de email desde el perfil sea consistente con el resto.
    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: Optional[str]) -> Optional[str]:
        return normalize_email(v) if v is not None else v


