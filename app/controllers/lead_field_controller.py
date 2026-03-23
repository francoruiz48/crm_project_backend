from app.controllers.base_controller import BaseController
from app.services.lead_field_service import LeadFieldService
from app.schemas.lead_field_schema import LeadFieldCreate, LeadFieldDetailedResponse, LeadFieldResponse, LeadFieldUpdate
from app.core.constans import READ_WRITE

class LeadFieldController(BaseController):
    router_prefix = "/lead_fields"
    service = LeadFieldService
    schema_in = LeadFieldCreate
    schema_update = LeadFieldUpdate
    schema_out = LeadFieldResponse
    schema_out_detail = LeadFieldDetailedResponse
    enabled_methods = READ_WRITE

router = LeadFieldController.get_router()