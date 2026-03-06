from app.controllers.base_controller import BaseController
from app.services.lead_flow_service import LeadFlowService
from app.schemas.lead_flow_schema import (
    LeadFlowCreate, 
    LeadFlowResponse, 
    LeadFlowDetailedResponse,
    LeadFlowUpdate
)

class LeadFlowController(BaseController):
    router_prefix = "/lead_flows"
    service = LeadFlowService
    schema_in = LeadFlowCreate
    schema_update = LeadFlowUpdate
    schema_out = LeadFlowResponse
    schema_out_detail = LeadFlowDetailedResponse

    enabled_methods = {"GET_ALL", "GET_ONE", "POST", "PUT", "DELETE"}

router = LeadFlowController.get_router()