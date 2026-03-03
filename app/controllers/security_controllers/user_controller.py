from app.controllers.base_controller import BaseController
from app.models.security_models import Role, User, UserOrganization
from app.services.security_services.user_service import UserService
from app.schemas.security_schemas.user_schema import UserDetailResponse, UserResponse, UserCreate
from app.core.constans import READ_WRITE

class UserController(BaseController):
    router_prefix = "/users"
    service = UserService
    schema_in = UserCreate
    schema_out = UserResponse
    schema_out_detail = UserDetailResponse
    enabled_methods = READ_WRITE

    relationships = [
        (User.organizations_access, UserOrganization.roles, Role.permissions)
    ]

router = UserController.get_router()
