from app.controllers.base_controller import BaseController
from app.services.team_access_service import TeamWorkspaceAccessService
from app.schemas.team_access_schema import TeamWorkspaceAccessCreate, TeamWorkspaceAccessDetailedResponse, TeamWorkspaceAccessResponse

class TeamWorkspaceAccessController(BaseController):
    router_prefix = "/team_workspace_access"
    service = TeamWorkspaceAccessService
    schema_in = TeamWorkspaceAccessCreate
    schema_out = TeamWorkspaceAccessResponse
    schema_out_detail = TeamWorkspaceAccessDetailedResponse
    enabled_methods = {"GET_ALL", "GET_ONE", "POST", "DELETE"}

    allowed_filter_fields = {"team_id", "workspace_id"}

router = TeamWorkspaceAccessController.get_router()