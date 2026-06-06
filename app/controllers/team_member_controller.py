from app.controllers.base_controller import BaseController
from app.services.team_member_service import TeamMemberService
from app.schemas.team_member_schema import TeamMemberCreate, TeamMemberDetailedResponse, TeamMemberResponse, TeamMemberUpdate
from app.core.constans import READ_WRITE

class TeamMemberController(BaseController):
    router_prefix = "/team_members"
    service = TeamMemberService
    schema_in = TeamMemberCreate
    schema_update = TeamMemberUpdate
    schema_out = TeamMemberResponse
    schema_out_detail = TeamMemberDetailedResponse
    enabled_methods = READ_WRITE

    allowed_filter_fields = {"team_id", "user_id", "role"}

router = TeamMemberController.get_router()