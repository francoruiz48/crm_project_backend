from typing import List, Union, Optional
from fastapi import Body, Depends, Query
from app.controllers.base_controller import BaseController
from app.core.constans import DEFAULT_PAGE_SIZE, PAGE_SIZE_LIMIT
from app.core.security import PermissionChecker, get_current_user
from app.models.lead import Lead
from app.models.lead_field import LeadField
from app.models.lead_field_value import LeadFieldValue
from app.schemas.filter_schema import LeadSearchRequest
from app.schemas.pagination_schema import PaginatedResponse
from app.services.lead_service import LeadService
from app.schemas.lead_schema import LeadCreate, LeadDetailedResponse, LeadResponse

class LeadController(BaseController):
    router_prefix = "/leads"
    service = LeadService
    schema_in = LeadCreate
    schema_out = LeadResponse
    schema_out_detail = LeadDetailedResponse

    relationships = [
        (Lead.field_values, LeadFieldValue.field, LeadField.field_type),
        (Lead.field_values, LeadFieldValue.field, LeadField.campaign)
    ]
    
    # Quitamos "GET_ALL" de aquí para que BaseController NO genere el default
    enabled_methods = {"GET_ONE", "POST", "PUT", "DELETE"} 

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

        @router.post("/search", 
            response_model=ResponseModelPaginated,
            dependencies=cls._get_deps("read")
        )
        def search_leads(
            page: int = Query(1, ge=1),
            page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=PAGE_SIZE_LIMIT),
            search_req: LeadSearchRequest = Body(...),
            detailed: bool = Query(False)
        ):

            total, items_pydantic = cls.service.search(
                page=page,
                page_size=page_size,
                search_req=search_req, 
                detailed=detailed
            )
            
            return PaginatedResponse.create(
                items=items_pydantic,
                total=total,
                page=page,
                page_size=page_size
            )


        @router.get("/", response_model=ResponseModelPaginated,
                dependencies=cls._get_deps("read"))
        def get_all(
            page: int = Query(1, ge=1),
            page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=PAGE_SIZE_LIMIT),
            only_active: bool = True, 
            detailed: bool = Query(False),
            campaign_id: Optional[int] = Query(None, description="Filtrar por ID de campaña")
        ):

            total, items_pydantic = cls.service.get_all(
                    page=page, 
                    page_size=page_size, 
                    only_active=only_active,
                    detailed=detailed,
                    campaign_id=campaign_id
                )

            return PaginatedResponse.create(
                items=items_pydantic,
                total=total,
                page=page,
                page_size=page_size
            )
   

        return router

router = LeadController.get_router()