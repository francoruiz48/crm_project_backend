from app.controllers.base_controller import BaseController
from app.services.lead_state_history_service import LeadStateHistoryService
from app.schemas.lead_state_history_schema import (
    LeadStateHistoryResponse, 
    LeadStateHistoryDetailedResponse
)
from typing import Union
from app.schemas.pagination_schema import PaginatedResponse
from app.core.constans import DEFAULT_PAGE_SIZE
from fastapi import Query

class LeadStateHistoryController(BaseController):
    router_prefix = "/lead_state_history"
    service = LeadStateHistoryService
    schema_out = LeadStateHistoryResponse
    schema_out_detail = LeadStateHistoryDetailedResponse

    enabled_methods = {"GET ONE"}

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
            lead_id: int = Query(..., ge=1, description="ID del lead para el cual obtener historial"),
        ):

            total, items_pydantic = cls.service.get_all(
                    page=page, 
                    page_size=page_size, 
                    only_active=only_active,
                    detailed=detailed,
                    lead_id=lead_id
                )

            return PaginatedResponse.create(
                items=items_pydantic,
                total=total,
                page=page,
                page_size=page_size
            )
        
        return router

router = LeadStateHistoryController.get_router()