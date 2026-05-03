from app.controllers.base_controller import BaseController
from app.services.lead_contact_state_service import LeadContactStateService
from app.schemas.lead_contact_state_schema import LeadContactStateDetailedResponse, LeadContactStateResponse, LeadContactStateCreate, LeadContactStateUpdate
from app.core.constans import READ_WRITE

class LeadContactStateController(BaseController):
    router_prefix = "/lead_contact_states"
    service = LeadContactStateService
    schema_in = LeadContactStateCreate
    schema_update = LeadContactStateUpdate
    schema_out = LeadContactStateResponse
    schema_out_detail = LeadContactStateDetailedResponse
    enabled_methods = READ_WRITE

router = LeadContactStateController.get_router()
