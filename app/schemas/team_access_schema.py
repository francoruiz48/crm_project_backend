from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field


class TeamWorkspaceAccessBase(BaseModel):
    team_id: int = Field(..., gt=0)
    workspace_id: int = Field(..., gt=0)

class TeamWorkspaceAccessCreate(TeamWorkspaceAccessBase, BaseCreate):
    pass


class TeamWorkspaceAccessResponse(TeamWorkspaceAccessBase, BaseResponse):
    pass

class TeamWorkspaceAccessDetailedResponse(TeamWorkspaceAccessBase, BaseDetailResponse):
    pass

# --------------------------------------------------

class TeamCampaignAccessBase(BaseModel):
    team_id: int = Field(..., gt=0)
    campaign_id: int = Field(..., gt=0)

class TeamCampaignAccessCreate(TeamCampaignAccessBase, BaseCreate):
    pass


class TeamCampaignAccessResponse(TeamCampaignAccessBase, BaseResponse):
    pass

class TeamCampaignAccessDetailedResponse(TeamCampaignAccessBase, BaseDetailResponse):
    pass



