

from sqlalchemy import or_
from app.db.repository.base_repository import BaseRepository
from app.models.campaign import Campaign
from app.models.team_access import TeamCampaignAccess, TeamWorkspaceAccess
from app.models.team_member import TeamMember
from app.models.workspace import Workspace
from app.schemas.campaign_schema import CampaignCreate, CampaignDetailedResponse, CampaignResponse

class CampaignRepository(BaseRepository):
    model = Campaign
    schema_in = CampaignCreate
    schema_out = CampaignResponse
    schema_out_detail = CampaignDetailedResponse


    @classmethod
    def apply_security_filter(cls, session, query, consulted_by: int, is_super_admin: bool = False):
        if is_super_admin:
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
    def get_all(cls, session, only_active: bool = True, detailed: bool = False, base_query=None, **kwargs):
        # 1. Armamos el query base
        query = base_query if base_query is not None else session.query(cls.model)
        
        # 2. Extraemos el consulted_by de los kwargs (si no viene, será None)
        consulted_by = kwargs.pop('consulted_by', None)
        is_super_admin = kwargs.pop('is_super_admin', False)
        
        # 3. Le inyectamos la Bóveda de seguridad SOLO si viene un consulted_by
        if consulted_by is not None:
            query = cls.apply_security_filter(session, query, consulted_by, is_super_admin)

        # 4. Llamamos al padre pasándole el query blindado y el resto de los kwargs intactos
        return super().get_all(
            session=session, 
            only_active=only_active, 
            detailed=detailed, 
            base_query=query, 
            **kwargs
        )