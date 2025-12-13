from app.controllers.base_controller import BaseController
from app.services.validation_rule_service import ValidationRuleService
from app.schemas.validation_rule_schema import ValidationRuleCreate, ValidationRuleResponse
from app.core.constans import READ_WRITE

class ValidationRuleController(BaseController):
    router_prefix = "/validation_rules"
    service = ValidationRuleService
    schema_in = ValidationRuleCreate
    schema_out = ValidationRuleResponse
    enabled_methods = READ_WRITE

router = ValidationRuleController.get_router()
