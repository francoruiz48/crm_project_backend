from app.controllers.base_controller import BaseController
from app.services.lead_field_section_service import LeadFieldSectionService
from app.schemas.lead_field_section_schema import LeadFieldSectionDetailedResponse, LeadFieldSectionResponse, LeadFieldSectionCreate, LeadFieldSectionUpdate
from app.core.constans import READ_WRITE

class LeadFieldSectionController(BaseController):
    router_prefix = "/lead_field_sections"
    service = LeadFieldSectionService
    schema_in = LeadFieldSectionCreate
    schema_update = LeadFieldSectionUpdate
    schema_out = LeadFieldSectionResponse
    schema_out_detail = LeadFieldSectionDetailedResponse
    enabled_methods = READ_WRITE

    allowed_filter_fields = {"name"}

router = LeadFieldSectionController.get_router()
