from app.controllers.base_controller import BaseController
from app.services.lead_state_service import LeadStateService
from app.schemas.lead_state_schema import LeadStateCreate, LeadStateResponse, LeadStateDetailedResponse

class LeadStateController(BaseController):
    router_prefix = "/lead_states"
    service = LeadStateService
    schema_in = LeadStateCreate
    schema_out = LeadStateResponse
    schema_out_detail = LeadStateDetailedResponse

    enabled_methods = {"GET_ALL", "GET_ONE", "POST", "PUT", "DELETE", "ACTIVE"}

router = LeadStateController.get_router()