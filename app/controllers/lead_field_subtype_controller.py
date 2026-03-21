from app.controllers.base_controller import BaseController
from app.services.lead_field_subtype_service import LeadFieldSubtypeService
from app.schemas.lead_field_subtype_schema import LeadFieldSubtypeDetailedResponse, LeadFieldSubtypeResponse
from app.core.constans import READ_ONLY

class LeadFieldSubtypeController(BaseController):
    router_prefix = "/lead_field_subtypes"
    service = LeadFieldSubtypeService   
    schema_out = LeadFieldSubtypeResponse
    schema_out_detail = LeadFieldSubtypeDetailedResponse
    enabled_methods = READ_ONLY

router = LeadFieldSubtypeController.get_router()