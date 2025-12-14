from app.controllers.base_controller import BaseController
from app.core.templates.rule_templates import STANDARD_RULES
from app.services.validation_rule_service import ValidationRuleService
from app.schemas.validation_rule_schema import ValidationRuleCreate, ValidationRuleResponse, ValidationTemplateResponse
from app.core.constans import READ_WRITE

class ValidationRuleController(BaseController):
    router_prefix = "/validation_rules"
    service = ValidationRuleService
    schema_in = ValidationRuleCreate
    schema_out = ValidationRuleResponse
    enabled_methods = READ_WRITE

router = ValidationRuleController.get_router()

@router.get("/templates", response_model=list[ValidationTemplateResponse])
def get_validation_templates():
    """Devuelve la lista de reglas predefinidas disponibles."""
    templates = []
    for key, t in STANDARD_RULES.items():
        templates.append({
            "code": t.code,
            "name": t.name,
            "description": t.description,
            "required_params": t.params,
            "error_message": t.error_message
        })
    return templates


last_route = router.routes.pop()

router.routes.insert(0, last_route)