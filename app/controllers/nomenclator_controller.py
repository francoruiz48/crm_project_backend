from app.controllers.base_controller import BaseController
from app.services.nomenclator_service import NomenclatorService
from app.schemas.nomenclator_schema import NomenclatorCreate, NomenclatorResponse, NomenclatorDetailedResponse, NomenclatorUpdate
from app.core.constans import READ_WRITE

class NomenclatorController(BaseController):
    router_prefix = "/nomenclators"
    service = NomenclatorService
    schema_in = NomenclatorCreate
    schema_update = NomenclatorUpdate
    schema_out = NomenclatorResponse
    schema_out_detail = NomenclatorDetailedResponse
    enabled_methods = READ_WRITE
    allowed_filter_fields = {"name", "parent_nomenclator_id"}

router = NomenclatorController.get_router()
