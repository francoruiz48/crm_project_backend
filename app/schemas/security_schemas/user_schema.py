from typing import List, Optional, Any
from pydantic import BaseModel, Field, field_validator
from app.schemas.base_schema import BaseCreate, BaseDetailResponse
from app.schemas.security_schemas.permission_schema import PermissionResponse
from app.schemas.security_schemas.role_schema import RoleDetailResponse, RoleResponse

class UserBase(BaseModel):
    email: str
    active: bool = True
    organization_id: Optional[int] = Field(default=None, gt=0)

class UserResponse(UserBase, BaseDetailResponse):
    roles: Optional[list[RoleResponse]] = []
    

class UserDetailResponse(UserResponse):
    permission_objects: List[PermissionResponse] = []

    @field_validator('permission_objects', mode='before')
    @classmethod
    def extract_permissions(cls, v: Any, info: Any) -> Any:
        # 'v' es el valor que Pydantic intenta leer. 
        # Si viene del ORM, 'info.context' o el objeto raíz debería tener la data.
        # Pero en mode='before' con from_attributes, a veces 'v' es el objeto User completo si el campo no existe en __dict__
        
        # Truco: Accedemos al objeto ORM original si Pydantic no pudo resolverlo
        if v == [] or v is None:
            # No podemos acceder fácilmente al 'self' del ORM aquí en Pydantic V2 estándar sin contexto extra.
            pass
        
        return v

class UserCreate(UserBase, BaseCreate):
    pass


