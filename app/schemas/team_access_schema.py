from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field
from typing import Optional
from app.schemas.team_schema import TeamResponse
from app.schemas.workspace_schema import WorkspaceResponse
from app.schemas.campaign_schema import CampaignResponse


class TeamWorkspaceAccessBase(BaseModel):
    team_id: int = Field(..., gt=0)
    workspace_id: int = Field(..., gt=0)

class TeamWorkspaceAccessCreate(TeamWorkspaceAccessBase, BaseCreate):
    # public_uuid de Team/Workspace (Fase 3). El Response sigue con el int interno viejo (FK
    # embebida, deliberadamente sin migrar -- ver backend/AGENTS.md §18). No hace falta lógica
    # extra en el service: get_all()/create() de BaseRepository ya resuelven estas FKs solos.
    team_id: str
    workspace_id: str


class TeamWorkspaceAccessResponse(TeamWorkspaceAccessBase, BaseResponse):
    # Fase 4: objeto anidado con el uuid real (ver backend/AGENTS.md §18), team_id/
    # workspace_id de arriba siguen siendo la FK embebida sin migrar.
    team: Optional[TeamResponse] = None
    workspace: Optional[WorkspaceResponse] = None

class TeamWorkspaceAccessDetailedResponse(TeamWorkspaceAccessBase, BaseDetailedResponse):
    team: Optional[TeamResponse] = None
    workspace: Optional[WorkspaceResponse] = None

# --------------------------------------------------

class TeamCampaignAccessBase(BaseModel):
    team_id: int = Field(..., gt=0)
    campaign_id: int = Field(..., gt=0)

class TeamCampaignAccessCreate(TeamCampaignAccessBase, BaseCreate):
    # public_uuid de Team/Campaign (Fase 3). El Response sigue con el int interno viejo (FK
    # embebida, deliberadamente sin migrar -- ver backend/AGENTS.md §18). No hace falta lógica
    # extra en el service: get_all()/create() de BaseRepository ya resuelven estas FKs solos.
    team_id: str
    campaign_id: str


class TeamCampaignAccessResponse(TeamCampaignAccessBase, BaseResponse):
    # Fase 4: objeto anidado con el uuid real (ver backend/AGENTS.md §18), team_id/
    # campaign_id de arriba siguen siendo la FK embebida sin migrar.
    team: Optional[TeamResponse] = None
    campaign: Optional[CampaignResponse] = None

class TeamCampaignAccessDetailedResponse(TeamCampaignAccessBase, BaseDetailedResponse):
    team: Optional[TeamResponse] = None
    campaign: Optional[CampaignResponse] = None



