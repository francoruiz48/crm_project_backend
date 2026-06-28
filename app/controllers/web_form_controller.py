from app.controllers.base_controller import BaseController
from app.services.web_form_service import WebFormService
from app.schemas.web_form_schema import WebFormCreate, WebFormDetailedResponse, WebFormResponse, WebFormUpdate
from app.core.constans import READ_WRITE

class WebFormController(BaseController):
    router_prefix = "/web_forms"
    service = WebFormService
    schema_in = WebFormCreate
    schema_update = WebFormUpdate
    schema_out = WebFormResponse
    schema_out_detail = WebFormDetailedResponse
    enabled_methods = READ_WRITE | {"DEACTIVATE"}

    allowed_filter_fields = {"campaign_id", "name", "description"}

router = WebFormController.get_router()