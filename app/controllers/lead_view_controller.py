from app.controllers.base_controller import BaseController
from app.services.lead_view_service import LeadViewService
from app.schemas.lead_view_schema import LeadViewCreate, LeadViewUpdate, LeadViewResponse, LeadViewDetailedResponse
from app.core.constans import READ_WRITE

class LeadViewController(BaseController):
    router_prefix = "/lead_views"
    service = LeadViewService
    schema_in = LeadViewCreate
    schema_update = LeadViewUpdate
    schema_out = LeadViewResponse
    schema_out_detail = LeadViewDetailedResponse
    
    enabled_methods = READ_WRITE

router = LeadViewController.get_router()