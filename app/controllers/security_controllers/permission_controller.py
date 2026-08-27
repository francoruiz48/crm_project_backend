from app.controllers.base_controller import BaseController
from app.services.security_services.permission_service import PermissionService
from app.schemas.security_schemas.permission_schema import PermissionResponse
from app.core.constans import READ_ONLY

class PermissionController(BaseController):
    router_prefix = "/permissions"
    service = PermissionService
    schema_out = PermissionResponse
    enabled_methods = READ_ONLY

router = PermissionController.get_router()
