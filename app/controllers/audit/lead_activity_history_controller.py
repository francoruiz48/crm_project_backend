from app.controllers.base_controller import BaseController
from app.services.audit.lead_activity_history_service import LeadActivityHistoryService
from app.schemas.audit.lead_activity_history_schema import LeadActivityHistoryResponse, LeadActivityHistoryDetailedResponse
from app.core.constans import READ_ONLY

class LeadActivityHistoryController(BaseController):
    router_prefix = "/lead-activity-histories"
    service = LeadActivityHistoryService
    schema_out = LeadActivityHistoryResponse
    schema_out_detail = LeadActivityHistoryDetailedResponse
    enabled_methods = READ_ONLY

router = LeadActivityHistoryController.get_router()