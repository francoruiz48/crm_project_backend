from app.controllers.base_controller import BaseController
from app.services.validation_rule_service import ValidationRuleService
from app.schemas.validation_rule_schema import ValidationRuleCreate, ValidationRuleDetailedResponse, ValidationRuleResponse, ValidationRuleUpdate
from app.core.constans import READ_WRITE

class ValidationRuleController(BaseController):
    router_prefix = "/validation_rules"
    service = ValidationRuleService
    schema_in = ValidationRuleCreate
    schema_update = ValidationRuleUpdate
    schema_out = ValidationRuleResponse
    schema_out_detail = ValidationRuleDetailedResponse
    enabled_methods = READ_WRITE

    allowed_filter_fields = {"name", "field_id", "template_code"}

router = ValidationRuleController.get_router()