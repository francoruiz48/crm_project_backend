from typing import List
from fastapi import Body, Depends
from pydantic import BaseModel

from app.controllers.base_controller import BaseController
from app.core.security import get_current_user_roles
from app.services.security_services.role_service import RoleService
from app.schemas.security_schemas.role_schema import RoleDetailedResponse, RoleResponse, RoleCreate, RoleUpdate
from app.core.constans import READ_WRITE


class RolePermissionsUpdate(BaseModel):
    # UUIDs públicos de Permission. Reemplaza TODO el set de permisos del rol
    # (no es incremental): mandar la lista completa deseada, incluida vacía [].
    permission_ids: List[str]


class RoleController(BaseController):
    router_prefix = "/roles"
    service = RoleService
    schema_in = RoleCreate
    schema_update = RoleUpdate
    schema_out = RoleResponse
    schema_out_detail = RoleDetailedResponse
    enabled_methods = READ_WRITE

    @classmethod
    def get_router(cls):
        router = super().get_router()

        # Protegido con "role:update": cambiar los permisos de un rol se trata como
        # una forma de editar ese rol (misma decisión que ya rige name/code por PUT).
        # cls._get_deps("update") resuelve solo a ese codename (ver BaseController).
        @router.put(
            "/{role_id}/permissions",
            response_model=cls.schema_out_detail,
            dependencies=cls._get_deps("update"),
        )
        def set_permissions(
            role_id: str,
            payload: RolePermissionsUpdate = Body(...),
            user_context=Depends(get_current_user_roles),
        ):
            return cls.service.set_permissions(role_id, payload.permission_ids, user_context=user_context)

        return router


router = RoleController.get_router()
