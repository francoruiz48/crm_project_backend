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
        if action in ("create", "read"):
            # Chicken-and-egg: para listar/crear organizaciones el usuario aún
            # no tiene una org seleccionada, así que no puede tener X-Organization-Id.
            # La autorización real se delega al servicio (filtra por membresía).
            return []
        return super()._get_deps(action)

router = OrganizationController.get_router()
