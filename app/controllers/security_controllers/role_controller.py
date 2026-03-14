from app.controllers.base_controller import BaseController
from app.services.security_services.role_service import RoleService
from app.schemas.security_schemas.role_schema import RoleDetailResponse, RoleResponse, RoleCreate, RoleUpdate
from app.core.constans import READ_WRITE

class RoleController(BaseController):
    router_prefix = "/roles"
    service = RoleService
    schema_in = RoleCreate
    schema_update = RoleUpdate
    schema_out = RoleResponse
    schema_out_detail = RoleDetailResponse
    enabled_methods = READ_WRITE

router = RoleController.get_router()
