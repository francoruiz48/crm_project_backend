from typing import List, Optional, Union
from fastapi import Query
from app.controllers.base_controller import BaseController
from app.core.constans import DEFAULT_PAGE_SIZE, PAGE_SIZE_LIMIT
from app.schemas.pagination_schema import PaginatedResponse
from app.services.nomenclator_item_service import NomenclatorItemService
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse, NomenclatorItemCreate, NomenclatorItemDetailResponse

class NomenclatorItemController(BaseController):
    router_prefix = "/nomenclator_items"
    service = NomenclatorItemService
    schema_in = NomenclatorItemCreate
    schema_out = NomenclatorItemResponse
    schema_out_detail = NomenclatorItemDetailResponse
    
    enabled_methods = {"GET_ONE", "POST", "PUT", "DELETE"} 

    @classmethod
    def get_router(cls):
        router = super().get_router()

        if cls.schema_out_detail:
            ResponseModelItem = Union[cls.schema_out_detail, cls.schema_out]
        else:
            ResponseModelItem = cls.schema_out
            
        ResponseModelPaginated = PaginatedResponse[ResponseModelItem]

        # 2. Definimos nuestro GET_ALL personalizado
        @router.get("/", response_model=PaginatedResponse)
        def get_all(
            page: int = Query(1, ge=1),
            page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=PAGE_SIZE_LIMIT),
            only_active: bool = True,
            detailed: bool = Query(False),
            nomenclator_id: Optional[int] = Query(None, description="Filtrar por ID de Nomenclador"),
            parent_item_id: Optional[int] = Query(None, description="Filtrar por ID del padre del item")
        ):
            # Llamamos al servicio pasando el filtro
            total, data = cls.service.get_all(
                page=page,
                page_size=page_size,
                only_active=only_active, 
                detailed=detailed, 
                nomenclator_id=nomenclator_id,
                parent_item_id = parent_item_id
            )
            
            return PaginatedResponse.create(
                items=data,
                total=total,
                page=page,
                page_size=page_size
            )
        return router

router = NomenclatorItemController.get_router()
