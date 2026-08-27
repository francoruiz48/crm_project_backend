

from typing import Optional

from sqlalchemy import or_
from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.campaign import Campaign
from app.models.team_access import TeamCampaignAccess, TeamWorkspaceAccess
from app.models.team_member import TeamMember
from app.models.workspace import Workspace
from app.schemas.campaign_schema import CampaignCreate, CampaignDetailedResponse, CampaignResponse
from app.core.security import UserContext

class CampaignRepository(BaseRepository):
    model = Campaign
    delete_strategy = DeleteStrategy.SOFT_DELETE_HARD_OPT
    schema_in = CampaignCreate
    schema_out = CampaignResponse
    schema_out_detail = CampaignDetailedResponse


    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext = None):

        if user_context is None or user_context.user is None:
            return query
        
        consulted_by = user_context.user.id

        if user_context.is_superuser or user_context.is_owner:
            return query

        user_team_ids = session.query(TeamMember.team_id).filter(
            TeamMember.user_id == consulted_by
        )

        # 1. Campañas con acceso directo
        direct_camp_ids = session.query(TeamCampaignAccess.campaign_id).filter(
            TeamCampaignAccess.team_id.in_(user_team_ids)
        )

        # 2. Campañas heredadas (el usuario tiene acceso al workspace padre)
        inherited_camp_ids = session.query(Campaign.id).join(
            Workspace, Campaign.workspace_id == Workspace.id
        ).join(
            TeamWorkspaceAccess, Workspace.id == TeamWorkspaceAccess.workspace_id
        ).filter(
            TeamWorkspaceAccess.team_id.in_(user_team_ids)
        )

        return query.filter(
            or_(
                cls.model.is_public == True,           # 1. Es pública
                cls.model.created_by == consulted_by,       # 2. Soy el dueño/creador
                cls.model.id.in_(direct_camp_ids),     # 3. Mi equipo tiene acceso directo
                cls.model.id.in_(inherited_camp_ids)   # 4. Mi equipo tiene acceso heredado
            )
        )

    @classmethod
    def get_accessible_campaign_ids(cls, session, user_context: Optional[UserContext] = None) -> set:
        """
        Devuelve el conjunto de IDs de campaña a los que el usuario tiene acceso, reutilizando
        exactamente la misma regla que apply_security_filter (para no duplicar la lógica de
        is_public/TeamCampaignAccess/TeamWorkspaceAccess). Se usa para redactar, en la respuesta
        de un lead, los datos de leads relacionados (campo tipo LEAD) que pertenezcan a una
        campaña a la que el usuario no tiene acceso (ver LeadService._redact_inaccessible_related_leads).
        """
        query = cls.apply_security_filter(session, session.query(cls.model.id), user_context)
        return {row[0] for row in query.all()}