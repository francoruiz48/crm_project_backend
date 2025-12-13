from app.controllers.base_controller import BaseController
from app.services.lead_service import LeadService
from app.schemas.lead_schema import LeadCreate, LeadResponse
from app.core.constans import READ_WRITE

class LeadController(BaseController):
    router_prefix = "/leads"
    service = LeadService
    schema_in = LeadCreate
    schema_out = LeadResponse
    enabled_methods = READ_WRITE

router = LeadController.get_router()
