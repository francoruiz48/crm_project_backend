
from sqlalchemy import or_
from app.db.repository.base_repository import BaseRepository
from app.models.campaign import Campaign
from app.models.team_access import TeamCampaignAccess, TeamWorkspaceAccess
from app.models.team_member import TeamMember
from app.models.workspace import Workspace
from app.schemas.workspace_schema import WorkspaceCreate, WorkspaceDetailedResponse, WorkspaceResponse

class WorkspaceRepository(BaseRepository):
    model = Workspace
    schema_in = WorkspaceCreate
    schema_out = WorkspaceResponse
    schema_out_detail = WorkspaceDetailedResponse


    @classmethod
    def apply_security_filter(cls, session, query, user_id: int, is_super_admin: bool = False):
        if is_super_admin:
            return query
        
        # 1. Obtenemos los IDs de los equipos a los que pertenece el usuario
        user_team_ids = session.query(TeamMember.team_id).filter(
            TeamMember.user_id == user_id
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
                cls.model.created_by == user_id,       # 2. Soy el dueño/creador
                cls.model.id.in_(direct_ws_ids),       # 3. Mi equipo tiene acceso directo
                cls.model.id.in_(inherited_ws_ids)     # 4. Mi equipo tiene acceso heredado
            )
        )
    

    @classmethod
    def get_all(cls, session, only_active: bool = True, detailed: bool = False, base_query=None, **kwargs):
        # 1. Armamos el query base
        query = base_query if base_query is not None else session.query(cls.model)

        is_super_admin = kwargs.pop('is_super_admin', False)
        
        # 2. Extraemos el user_id de los kwargs (si no viene, será None)
        user_id = kwargs.pop('user_id', None)
        
        # 3. Le inyectamos la Bóveda de seguridad SOLO si viene un user_id
        if user_id is not None:
            query = cls.apply_security_filter(session, query, user_id, is_super_admin)

        # 4. Llamamos al padre pasándole el query blindado y el resto de los kwargs intactos
        return super().get_all(
            session=session, 
            only_active=only_active, 
            detailed=detailed, 
            base_query=query, 
            **kwargs
        )
