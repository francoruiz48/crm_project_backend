from app.controllers.base_controller import BaseController
from app.schemas.pagination_schema import PaginatedResponse
from app.services.workspace_service import WorkspaceService
from app.schemas.workspace_schema import WorkspaceDetailedResponse, WorkspaceResponse, WorkspaceCreate, WorkspaceUpdate
from app.core.constans import DEFAULT_PAGE_SIZE
from typing import Optional, Union
from app.core.security import get_current_user
from fastapi import Query, Depends

class WorkspaceController(BaseController):
    router_prefix = "/workspaces"
    service = WorkspaceService
    schema_in = WorkspaceCreate
    schema_update = WorkspaceUpdate
    schema_out = WorkspaceResponse
    schema_out_detail = WorkspaceDetailedResponse
    enabled_methods = {"GET_ONE", "POST", "PUT", "DELETE", "ACTIVE"}

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

        @router.get("/", response_model=ResponseModelPaginated,
                dependencies=cls._get_deps("read"))
        def get_all(
            page: int = Query(1, ge=1),
            page_size: int = DEFAULT_PAGE_SIZE,
            only_active: bool = True, 
            detailed: bool = Query(False),
            search: Optional[str] = Query(None, description="Buscar dentro de workspaces"),
            current_user = Depends(get_current_user)
        ):
            super_admin_flag = getattr(current_user, 'is_superuser', False)

            total, items_pydantic = cls.service.get_all(user_id=current_user.id,
                    page=page, 
                    page_size=page_size, 
                    is_super_admin=super_admin_flag,
                    only_active=only_active,
                    detailed=detailed,
                    search=search, search_fields=['name'],
                )

            return PaginatedResponse.create(
                items=items_pydantic,
                total=total,
                page=page,
                page_size=page_size
            )
   
        return router

router = WorkspaceController.get_router()
