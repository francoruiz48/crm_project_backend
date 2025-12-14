from app.controllers.base_controller import BaseController
from app.services.nomenclator_service import NomenclatorService
from app.schemas.nomenclator_schema import NomenclatorCreate, NomenclatorResponse
from app.core.constans import READ_WRITE

class NomenclatorController(BaseController):
    router_prefix = "/nomenclators"
    service = NomenclatorService
    schema_in = NomenclatorCreate
    schema_out = NomenclatorResponse
    enabled_methods = READ_WRITE

router = NomenclatorController.get_router()
