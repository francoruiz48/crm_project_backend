from app.controllers.base_controller import BaseController
from app.services.lead_field_type_service import LeadFieldTypeService
from app.schemas.lead_field_type_schema import LeadFieldTypeDetailedResponse, LeadFieldTypeResponse
from app.core.constans import READ_ONLY

class LeadFieldTypeController(BaseController):
    router_prefix = "/lead_field_types"
    service = LeadFieldTypeService
    schema_out = LeadFieldTypeResponse
    schema_out_detail = LeadFieldTypeDetailedResponse
    enabled_methods = READ_ONLY

router = LeadFieldTypeController.get_router()
