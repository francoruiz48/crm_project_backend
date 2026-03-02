from typing import Optional, Union

from fastapi import Query
from app.controllers.base_controller import BaseController
from app.schemas.pagination_schema import PaginatedResponse
from app.services.campaign_service import CampaignService
from app.schemas.campaign_schema import CampaignDetailedResponse, CampaignResponse, CampaignCreate
from app.core.constans import DEFAULT_PAGE_SIZE, PAGE_SIZE_LIMIT, READ_WRITE

class CampaignController(BaseController):
    router_prefix = "/campaigns"
    service = CampaignService
    schema_in = CampaignCreate
    schema_out = CampaignResponse
    schema_out_detail = CampaignDetailedResponse
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
            search: Optional[str] = Query(None, description="Buscar dentro de campañas"),
            workspace_id: Optional[int] = Query(None, description="ID del workspace para filtrar campañas")
        ):

            total, items_pydantic = cls.service.get_all(
                    page=page, 
                    page_size=page_size, 
                    only_active=only_active,
                    detailed=detailed,
                    search=search, search_fields=['name', 'description'],
                    workspace_id=workspace_id
                )

            return PaginatedResponse.create(
                items=items_pydantic,
                total=total,
                page=page,
                page_size=page_size
            )
   

        return router

router = CampaignController.get_router()
