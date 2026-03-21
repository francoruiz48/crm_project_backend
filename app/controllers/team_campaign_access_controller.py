from app.controllers.base_controller import BaseController
from app.services.team_access_service import TeamCampaignAccessService
from app.schemas.team_access_schema import TeamCampaignAccessCreate, TeamCampaignAccessDetailedResponse, TeamCampaignAccessResponse
from app.core.constans import READ_WRITE

class TeamCampaignAccessController(BaseController):
    router_prefix = "/team_campaign_access"
    service = TeamCampaignAccessService
    schema_in = TeamCampaignAccessCreate
    schema_out = TeamCampaignAccessResponse
    schema_out_detail = TeamCampaignAccessDetailedResponse
    enabled_methods = {"GET_ALL", "GET_ONE", "POST", "DELETE"}

router = TeamCampaignAccessController.get_router()