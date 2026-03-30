from typing import Union
from fastapi import Depends, Query
from app.controllers.base_controller import BaseController
from app.models.security_models import Role, User, UserOrganization
from app.services.security_services.user_service import UserService
from app.schemas.security_schemas.user_schema import UserDetailedResponse, UserResponse, UserCreate, UserUpdate
from app.core.constans import READ_WRITE
from app.schemas.pagination_schema import PaginatedResponse
from app.core.security import get_current_user_roles

class UserController(BaseController):
    router_prefix = "/users"
    service = UserService
    schema_in = UserCreate
    schema_update = UserUpdate
    schema_out = UserResponse
    schema_out_detail = UserDetailedResponse
    enabled_methods = READ_WRITE

    relationships = [
        (User.organizations_access, UserOrganization.roles, Role.permissions)
    ]

    @classmethod
    def get_router(cls):
        # Generamos el router con los métodos base (GET_ONE, POST, etc.)
        router = super().get_router()

        # Preparamos el modelo de respuesta (para Swagger)
        if cls.schema_out_detail:
            ResponseModelItem = Union[cls.schema_out_detail, cls.schema_out]
        else:
            ResponseModelItem = cls.schema_out
            
        ResponseModelPaginated = PaginatedResponse[ResponseModelItem]

        @router.patch("/promote_to_superuser/{id}", dependencies=cls._get_deps("update"))
        async def promote_to_superuser(
            id: int,
            user_context = Depends(get_current_user_roles)
        ):
            return cls.service.promote_to_superuser(target_user_id=id, user_context=user_context)
        
        @router.patch("/organization/{organization_id}/promote-owner/{user_id}", dependencies=cls._get_deps("update"))
        async def promote_to_org_owner(
            user_id: int,
            organization_id: int,
            user_context = Depends(get_current_user_roles)
        ):
            return cls.service.promote_to_org_owner(target_user_id=user_id, organization_id=organization_id, user_context=user_context)

        return router


router = UserController.get_router()
