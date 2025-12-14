from app.controllers.base_controller import BaseController
from app.services.nomenclator_item_service import NomenclatorItemService
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse, NomenclatorItemCreate
from app.core.constans import READ_WRITE

class NomenclatorItemController(BaseController):
    router_prefix = "/nomenclator_items"
    service = NomenclatorItemService
    schema_in = NomenclatorItemCreate
    schema_out = NomenclatorItemResponse
    enabled_methods = READ_WRITE

router = NomenclatorItemController.get_router()
