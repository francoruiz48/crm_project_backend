from app.controllers.base_controller import BaseController
from app.services.organization_service import OrganizationService
from app.schemas.organization_schema import OrganizationDetailedResponse, OrganizationResponse, OrganizationCreate, OrganizationUpdate
from app.core.constans import READ_WRITE

class OrganizationController(BaseController):
    router_prefix = "/organizations"
    service = OrganizationService
    schema_in = OrganizationCreate
    schema_update = OrganizationUpdate
    schema_out = OrganizationResponse
    schema_out_detail = OrganizationDetailedResponse
    enabled_methods = READ_WRITE

    allowed_filter_fields = {"name", "description"}

    @classmethod
    def _get_deps(cls, action: str):
        if action == "create":
            # Cualquier usuario autenticado puede crear su primera organización.
            # El límite (1 org por usuario no-superadmin) se valida en OrganizationService.
            # Retornar deps vacíos evita el problema chicken-and-egg:
            # el usuario necesitaría pertenecer a una org para tener permiso de crear una.
            return []
        return super()._get_deps(action)

router = OrganizationController.get_router()
