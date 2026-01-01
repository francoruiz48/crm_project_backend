from app.controllers.base_controller import BaseController
from app.core.templates.field_templates import STANDARD_FIELD_TEMPLATES
from app.services.lead_field_service import LeadFieldService
from app.schemas.lead_field_schema import LeadFieldCreate, LeadFieldDetailedResponse, LeadFieldResponse, LeadFieldTemplateResponse
from app.core.constans import READ_WRITE


class LeadFieldController(BaseController):
    router_prefix = "/lead_fields"
    service = LeadFieldService
    schema_in = LeadFieldCreate
    schema_out = LeadFieldResponse
    schema_out_detail = LeadFieldDetailedResponse
    enabled_methods = READ_WRITE


router = LeadFieldController.get_router()

@router.get("/templates", response_model=list[LeadFieldTemplateResponse])
def get_lead_fields_templates():
    templates = []
    for key, t in STANDARD_FIELD_TEMPLATES.items():
        templates.append({
            "code": key,
            "name": t.name,
            "field_type_code": t.field_type_code,
            "rules": t.rules
        })
    return templates


last_route = router.routes.pop()

router.routes.insert(0, last_route)