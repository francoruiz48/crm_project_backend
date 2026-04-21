from typing import Optional
from app.core.security import UserContext
from app.db.repository.base_repository import BaseRepository
from app.models.team_access import TeamCampaignAccess, TeamWorkspaceAccess
from app.models.team import Team
from app.schemas.team_access_schema import (
    TeamCampaignAccessCreate, TeamCampaignAccessDetailedResponse, TeamCampaignAccessResponse,
    TeamWorkspaceAccessCreate, TeamWorkspaceAccessDetailedResponse, TeamWorkspaceAccessResponse,
)
from fastapi import HTTPException, status
 
 
class TeamWorkspaceAccessRepository(BaseRepository):
    model             = TeamWorkspaceAccess
    schema_in         = TeamWorkspaceAccessCreate
    schema_out        = TeamWorkspaceAccessResponse
    schema_out_detail = TeamWorkspaceAccessDetailedResponse
 
    @classmethod
    def create(cls, session, obj_data=None, user_context: Optional[UserContext] = None):
        from app.core.context import TENANT_ORG_ID
        from app.models.workspace import Workspace
        org_id = TENANT_ORG_ID.get()
        data   = cls._normalize_data(obj_data)
        if org_id:
            team = session.query(Team).filter_by(id=data.get("team_id")).first()
            if not team or team.organization_id != org_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "team_id",
                             "message": "El equipo no existe o no pertenece a esta organización."}])
            ws = session.query(Workspace).filter_by(id=data.get("workspace_id")).first()
            if not ws or ws.organization_id != org_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "workspace_id",
                             "message": "El workspace no existe o no pertenece a esta organización."}])
        return super().create(session, obj_data, user_context)
 
 
class TeamCampaignAccessRepository(BaseRepository):
    model             = TeamCampaignAccess
    schema_in         = TeamCampaignAccessCreate
    schema_out        = TeamCampaignAccessResponse
    schema_out_detail = TeamCampaignAccessDetailedResponse
 
    @classmethod
    def create(cls, session, obj_data=None, user_context: Optional[UserContext] = None):
        from app.core.context import TENANT_ORG_ID
        from app.models.campaign import Campaign
        org_id = TENANT_ORG_ID.get()
        data   = cls._normalize_data(obj_data)
        if org_id:
            team = session.query(Team).filter_by(id=data.get("team_id")).first()
            if not team or team.organization_id != org_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "team_id",
                             "message": "El equipo no existe o no pertenece a esta organización."}])
            camp = session.query(Campaign).filter_by(id=data.get("campaign_id")).first()
            if not camp or camp.organization_id != org_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "campaign_id",
                             "message": "La campaña no existe o no pertenece a esta organización."}])
        return super().create(session, obj_data, user_context)