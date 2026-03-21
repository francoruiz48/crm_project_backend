from typing import List, Optional, Union
from fastapi import Query
from app.controllers.base_controller import BaseController
from app.core.constans import DEFAULT_PAGE_SIZE, PAGE_SIZE_LIMIT, READ_WRITE
from app.schemas.pagination_schema import PaginatedResponse
from app.services.nomenclator_item_service import NomenclatorItemService
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse, NomenclatorItemCreate, NomenclatorItemDetailedResponse, NomenclatorItemUpdate

class NomenclatorItemController(BaseController):
    router_prefix = "/nomenclator_items"
    service = NomenclatorItemService
    schema_in = NomenclatorItemCreate
    schema_update = NomenclatorItemUpdate
    schema_out = NomenclatorItemResponse
    schema_out_detail = NomenclatorItemDetailedResponse
    
    enabled_methods = READ_WRITE

router = NomenclatorItemController.get_router()
