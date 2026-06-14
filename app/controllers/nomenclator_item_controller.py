from app.controllers.base_controller import BaseController
from app.core.constans import READ_WRITE
from app.services.nomenclator_item_service import NomenclatorItemService
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse, NomenclatorItemCreate, NomenclatorItemDetailedResponse, NomenclatorItemUpdate

class NomenclatorItemController(BaseController):
    router_prefix = "/nomenclator_items"
    service = NomenclatorItemService
    schema_in = NomenclatorItemCreate
    schema_update = NomenclatorItemUpdate
    schema_out = NomenclatorItemResponse
    schema_out_detail = NomenclatorItemDetailedResponse
    
    enabled_methods = READ_WRITE | {"DEACTIVATE"}

    allowed_filter_fields = {"value", "nomenclator_id", "parent_item_id"}

router = NomenclatorItemController.get_router()
