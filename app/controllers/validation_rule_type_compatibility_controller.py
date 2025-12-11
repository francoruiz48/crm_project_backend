from app.controllers.base_controller import BaseController
from app.services.validation_rule_type_compatibility_service import ValidationRuleTypeCompatibilityService
from app.schemas.validation_rule_type_compatibility_schema import ValidationRuleTypeCompatibilityCreate, ValidationRuleTypeCompatibilityResponse
from app.core.constans import READ_WRITE

class ValidationRuleTypeCompatibilityController(BaseController):
    router_prefix = "/validation_rule_type_compatibilities"
    service = ValidationRuleTypeCompatibilityService
    schema_in = ValidationRuleTypeCompatibilityCreate
    schema_out = ValidationRuleTypeCompatibilityResponse
    enabled_methods = READ_WRITE

router = ValidationRuleTypeCompatibilityController.get_router()
