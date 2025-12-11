from app.controllers.base_controller import BaseController
from app.services.validation_rule_type_service import ValidationRuleTypeService
from app.schemas.validation_rule_type_schema import ValidationRuleTypeResponse
from app.core.constans import READ_ONLY

class ValidationRuleTypeController(BaseController):
    router_prefix = "/validation_rule_types"
    service = ValidationRuleTypeService
    schema_out = ValidationRuleTypeResponse
    enabled_methods = READ_ONLY

router = ValidationRuleTypeController.get_router()
