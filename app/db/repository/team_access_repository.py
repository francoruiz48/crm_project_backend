from app.db.repository.base_repository import BaseRepository
from app.models.team_access import TeamCampaignAccess, TeamWorkspaceAccess
from app.schemas.team_access_schema import TeamCampaignAccessCreate, TeamCampaignAccessDetailedResponse, TeamCampaignAccessResponse, TeamWorkspaceAccessCreate, TeamWorkspaceAccessResponse, TeamWorkspaceAccessDetailedResponse

class TeamWorkspaceAccessRepository(BaseRepository):
    model = TeamWorkspaceAccess
    schema_in = TeamWorkspaceAccessCreate
    schema_out = TeamWorkspaceAccessResponse
    schema_out_detail = TeamWorkspaceAccessDetailedResponse

# -------------------------------------

class TeamCampaignAccessRepository(BaseRepository):
    model = TeamCampaignAccess
    schema_in = TeamCampaignAccessCreate
    schema_out = TeamCampaignAccessResponse
    schema_out_detail = TeamCampaignAccessDetailedResponse


