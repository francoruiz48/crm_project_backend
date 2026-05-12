from app.controllers.base_controller import BaseController
from app.services.field_automation_service import FieldAutomationService
from app.schemas.field_automation_schema import FieldAutomationCreate, FieldAutomationDetailedResponse, FieldAutomationResponse, FieldAutomationUpdate
from app.core.constans import READ_WRITE

class FieldAutomationController(BaseController):
    router_prefix = "/field_automations"
    service = FieldAutomationService
    schema_in= FieldAutomationCreate
    schema_update = FieldAutomationUpdate
    schema_out = FieldAutomationResponse
    schema_out_detail = FieldAutomationDetailedResponse
    enabled_methods = READ_WRITE

router = FieldAutomationController.get_router()