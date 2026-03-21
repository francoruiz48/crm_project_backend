from app.controllers.base_controller import BaseController
from app.services.team_service import TeamService
from app.schemas.team_schema import TeamCreate, TeamDetailedResponse, TeamResponse, TeamUpdate
from app.core.constans import READ_WRITE

class TeamController(BaseController):
    router_prefix = "/teams"
    service = TeamService
    schema_in = TeamCreate
    schema_update = TeamUpdate
    schema_out = TeamResponse
    schema_out_detail = TeamDetailedResponse
    enabled_methods = READ_WRITE

router = TeamController.get_router()