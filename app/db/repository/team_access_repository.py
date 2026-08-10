from typing import Optional
from app.core.constans import DeleteStrategy
from app.core.security import UserContext
from app.db.repository.base_repository import BaseRepository
from app.models.team_access import TeamCampaignAccess, TeamWorkspaceAccess
from app.models.team import Team
from app.schemas.team_access_schema import (
    TeamCampaignAccessCreate, TeamCampaignAccessDetailedResponse, TeamCampaignAccessResponse,
    TeamWorkspaceAccessCreate, TeamWorkspaceAccessDetailedResponse, TeamWorkspaceAccessResponse,
)
from app.db.repository.team_repository import TeamRepository
from fastapi import HTTPException, status


class TeamWorkspaceAccessRepository(BaseRepository):
    model             = TeamWorkspaceAccess
    delete_strategy = DeleteStrategy.HARD_DELETE_ALWAYS
    schema_in         = TeamWorkspaceAccessCreate
    schema_out        = TeamWorkspaceAccessResponse
    schema_out_detail = TeamWorkspaceAccessDetailedResponse

    @classmethod
    def create(cls, session, obj_data=None, user_context: Optional[UserContext] = None):
        from app.core.context import TENANT_ORG_ID
        from app.models.workspace import Workspace
        from app.db.repository.workspace_repository import WorkspaceRepository
        org_id = TENANT_ORG_ID.get()
        data   = cls._normalize_data(obj_data)
        # team_id/workspace_id llegan como public_uuid (Fase 3, ver backend/AGENTS.md §18);
        # se resuelven acá porque esta validación de organización corre ANTES del fix
        # genérico de BaseRepository.create() (_resolve_fk_payload_fields), que solo se
        # aplica dentro del super().create() de más abajo. Bug real encontrado durante
        # Fase 4 (nested objects): sin esto, la query de abajo comparaba el uuid crudo
        # contra Team.id (int interno) y esta validación fallaba SIEMPRE que hubiera
        # tenant context -- dar acceso a un workspace estaba roto en la práctica.
        team_internal_id = TeamRepository.get_internal_id_by_public_uuid(session, data.get("team_id"))
        workspace_internal_id = WorkspaceRepository.get_internal_id_by_public_uuid(session, data.get("workspace_id"))
        if team_internal_id is not None:
            data["team_id"] = team_internal_id
        if workspace_internal_id is not None:
            data["workspace_id"] = workspace_internal_id
        if org_id:
            team = session.query(Team).filter_by(id=team_internal_id).first()
            if not team or team.organization_id != org_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "team_id",
                             "message": "El equipo no existe o no pertenece a esta organización."}])
            ws = session.query(Workspace).filter_by(id=workspace_internal_id).first()
            if not ws or ws.organization_id != org_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "workspace_id",
                             "message": "El workspace no existe o no pertenece a esta organización."}])
        return super().create(session, data, user_context)


class TeamCampaignAccessRepository(BaseRepository):
    model             = TeamCampaignAccess
    schema_in         = TeamCampaignAccessCreate
    schema_out        = TeamCampaignAccessResponse
    schema_out_detail = TeamCampaignAccessDetailedResponse

    @classmethod
    def create(cls, session, obj_data=None, user_context: Optional[UserContext] = None):
        from app.core.context import TENANT_ORG_ID
        from app.models.campaign import Campaign
        from app.db.repository.campaign_repository import CampaignRepository
        org_id = TENANT_ORG_ID.get()
        data   = cls._normalize_data(obj_data)
        # Mismo bug/fix que en TeamWorkspaceAccessRepository.create() (ver comentario ahí).
        team_internal_id = TeamRepository.get_internal_id_by_public_uuid(session, data.get("team_id"))
        campaign_internal_id = CampaignRepository.get_internal_id_by_public_uuid(session, data.get("campaign_id"))
        if team_internal_id is not None:
            data["team_id"] = team_internal_id
        if campaign_internal_id is not None:
            data["campaign_id"] = campaign_internal_id
        if org_id:
            team = session.query(Team).filter_by(id=team_internal_id).first()
            if not team or team.organization_id != org_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "team_id",
                             "message": "El equipo no existe o no pertenece a esta organización."}])
            camp = session.query(Campaign).filter_by(id=campaign_internal_id).first()
            if not camp or camp.organization_id != org_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "campaign_id",
                             "message": "La campaña no existe o no pertenece a esta organización."}])
        return super().create(session, data, user_context)