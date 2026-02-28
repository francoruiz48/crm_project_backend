from typing import Optional, Union
from fastapi import Query
from app.controllers.base_controller import BaseController
from app.services.lead_field_service import LeadFieldService
from app.schemas.lead_field_schema import LeadFieldCreate, LeadFieldDetailedResponse, LeadFieldResponse
from app.core.constans import DEFAULT_PAGE_SIZE, PAGE_SIZE_LIMIT
from app.schemas.pagination_schema import PaginatedResponse


class LeadFieldController(BaseController):
    router_prefix = "/lead_fields"
    service = LeadFieldService
    schema_in = LeadFieldCreate
    schema_out = LeadFieldResponse
    schema_out_detail = LeadFieldDetailedResponse
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
            campaign_id: Optional[int] = Query(None, description="Filtrar por ID de campaña")
        ):

            total, items_pydantic = cls.service.get_all(
                    page=page, 
                    page_size=page_size, 
                    only_active=only_active,
                    detailed=detailed,
                    campaign_id=campaign_id,
                    order_by="order",
                    ascending=True
                )

            return PaginatedResponse.create(
                items=items_pydantic,
                total=total,
                page=page,
                page_size=page_size
            )
   

        return router

router = LeadFieldController.get_router()