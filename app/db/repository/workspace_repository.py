
from sqlalchemy import or_
from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.campaign import Campaign
from app.models.team_access import TeamCampaignAccess, TeamWorkspaceAccess
from app.models.team_member import TeamMember
from app.models.workspace import Workspace
from app.schemas.workspace_schema import WorkspaceCreate, WorkspaceDetailedResponse, WorkspaceResponse
from app.core.security import UserContext

class WorkspaceRepository(BaseRepository):
    model = Workspace
    delete_strategy = DeleteStrategy.SMART_DELETE
    delete_blockers = ["campaigns"]
    schema_in = WorkspaceCreate
    schema_out = WorkspaceResponse
    schema_out_detail = WorkspaceDetailedResponse


    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext = None):

        if user_context is None or user_context.user is None:
            return query
        
        consulted_by = user_context.user.id

        if user_context.is_superuser or user_context.is_owner:
            return query
        
        # 1. Obtenemos los IDs de los equipos a los que pertenece el usuario
        user_team_ids = session.query(TeamMember.team_id).filter(
            TeamMember.user_id == consulted_by
        )

        # 2. Workspaces con acceso directo
        direct_ws_ids = session.query(TeamWorkspaceAccess.workspace_id).filter(
            TeamWorkspaceAccess.team_id.in_(user_team_ids)
        )

        # 3. Workspaces heredados (el usuario tiene acceso a una campaña dentro de este ws)
        inherited_ws_ids = session.query(Campaign.workspace_id).join(
            TeamCampaignAccess, Campaign.id == TeamCampaignAccess.campaign_id
        ).filter(
            TeamCampaignAccess.team_id.in_(user_team_ids)
        )

        # 4. Aplicamos el filtro a la consulta original
        return query.filter(
            or_(
                cls.model.is_public == True,           # 1. Es público
                cls.model.created_by == consulted_by,       # 2. Soy el dueño/creador
                cls.model.id.in_(direct_ws_ids),       # 3. Mi equipo tiene acceso directo
                cls.model.id.in_(inherited_ws_ids)     # 4. Mi equipo tiene acceso heredado
            )
        )
    