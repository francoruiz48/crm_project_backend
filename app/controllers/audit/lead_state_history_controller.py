from app.controllers.base_controller import BaseController
from app.services.audit.lead_state_history_service import LeadStateHistoryService
from app.schemas.audit.lead_state_history_schema import (
    LeadStateHistoryResponse, 
    LeadStateHistoryDetailedResponse
)
from app.core.constans import READ_ONLY

class LeadStateHistoryController(BaseController):
    router_prefix = "/lead_state_history"
    service = LeadStateHistoryService
    schema_out = LeadStateHistoryResponse
    schema_out_detail = LeadStateHistoryDetailedResponse
    enabled_methods = READ_ONLY

router = LeadStateHistoryController.get_router()