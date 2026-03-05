from app.controllers.base_controller import BaseController
from app.services.lead_state_transition_service import LeadStateTransitionService
from app.schemas.lead_state_transition_schema import (
    LeadStateTransitionCreate, 
    LeadStateTransitionResponse, 
    LeadStateTransitionDetailedResponse
)

class LeadStateTransitionController(BaseController):
    router_prefix = "/lead_state_transitions"
    service = LeadStateTransitionService
    schema_in = LeadStateTransitionCreate
    schema_out = LeadStateTransitionResponse
    schema_out_detail = LeadStateTransitionDetailedResponse

    # Limitamos los métodos: No permitimos PUT (es mejor borrar y recrear la regla) ni ACTIVE
    enabled_methods = {"GET_ALL", "GET_ONE", "POST", "DELETE"}

router = LeadStateTransitionController.get_router()