from app.controllers.base_controller import BaseController
from app.services.organization_service import OrganizationService
from app.schemas.organization_schema import OrganizationDetailedResponse, OrganizationResponse, OrganizationCreate
from app.core.constans import READ_WRITE

class OrganizationController(BaseController):
    router_prefix = "/organizations"
    service = OrganizationService
    schema_in = OrganizationCreate
    schema_out = OrganizationResponse
    schema_out_detail = OrganizationDetailedResponse
    enabled_methods = READ_WRITE


router = OrganizationController.get_router()
