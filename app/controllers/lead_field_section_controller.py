from typing import Optional, Union
from fastapi import Query
from app.controllers.base_controller import BaseController
from app.schemas.pagination_schema import PaginatedResponse
from app.services.lead_field_section_service import LeadFieldSectionService
from app.schemas.lead_field_section_schema import LeadFieldSectionDetailedResponse, LeadFieldSectionResponse, LeadFieldSectionCreate, LeadFieldSectionUpdate
from app.core.constans import DEFAULT_PAGE_SIZE, PAGE_SIZE_LIMIT, READ_WRITE

class LeadFieldSectionController(BaseController):
    router_prefix = "/lead_field_sections"
    service = LeadFieldSectionService
    schema_in = LeadFieldSectionCreate
    schema_update = LeadFieldSectionUpdate
    schema_out = LeadFieldSectionResponse
    schema_out_detail = LeadFieldSectionDetailedResponse
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
            name: str = Query(None, description="Nombre")
        ):

            total, items_pydantic = cls.service.get_all(
                    page=page, 
                    page_size=page_size, 
                    only_active=only_active,
                    detailed=detailed,
                    name=name
                )

            return PaginatedResponse.create(
                items=items_pydantic,
                total=total,
                page=page,
                page_size=page_size
            )
   

        return router

router = LeadFieldSectionController.get_router()
