from pydantic import BaseModel

from app.schemas.base_schema import BaseResponse

# `PermissionResponse` debe exponer el id (public_uuid) igual que el resto de la API,
# porque el PermissionForm del frontend arma su selección con perm.id (ver roles.ts).
# Se hereda de BaseResponse (mismo patrón que WorkspaceLiteResponse/LeadFieldLiteResponse).
class PermissionResponse(BaseModel, BaseResponse):
    name: str
    codename: str



