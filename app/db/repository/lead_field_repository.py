from sqlalchemy import func, or_
from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.lead_field import LeadField
from app.schemas.lead_field_schema import LeadFieldDetailedResponse, LeadFieldResponse
from sqlalchemy.orm import joinedload
from app.core.security import UserContext
from app.models.campaign import Campaign
from app.models.team_access import TeamCampaignAccess, TeamWorkspaceAccess
from app.models.team_member import TeamMember
from app.models.workspace import Workspace

class LeadFieldRepository(BaseRepository):
    model = LeadField
    delete_strategy = DeleteStrategy.SMART_DELETE
    delete_blockers = ["field_values", "web_form_fields"]
    schema_out = LeadFieldResponse
    schema_out_detail = LeadFieldDetailedResponse

    relationships = [
        (LeadField.field_type,),
        (LeadField.validation_rules,),
    ]

    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext = None):
        """
        Filtra los LeadFields basándose en los permisos que el usuario tiene 
        sobre la Campaña a la que pertenecen.
        """
        if user_context is None or user_context.user is None:
            return query
        
        # Superusuarios y Owners saltan la validación (Bóveda abierta)
        if user_context.is_superuser or user_context.is_owner:
            return query

        consulted_by = user_context.user.id

        # 1. Obtener los IDs de los equipos a los que pertenece el usuario
        user_team_ids = session.query(TeamMember.team_id).filter(
            TeamMember.user_id == consulted_by
        ).subquery()

        # 2. Query de Campañas con acceso directo por equipo
        direct_camp_ids = session.query(TeamCampaignAccess.campaign_id).filter(
            TeamCampaignAccess.team_id.in_(user_team_ids)
        )

        # 3. Query de Campañas con acceso heredado vía Workspace
        inherited_camp_ids = session.query(Campaign.id).join(
            Workspace, Campaign.workspace_id == Workspace.id
        ).join(
            TeamWorkspaceAccess, Workspace.id == TeamWorkspaceAccess.workspace_id
        ).filter(
            TeamWorkspaceAccess.team_id.in_(user_team_ids)
        )

        # 4. Aplicar el filtro al query de LeadField
        # Filtramos LeadField basándonos en los atributos de su Campaign relacionada
        return query.join(Campaign, cls.model.campaign_id == Campaign.id).filter(
            or_(
                Campaign.is_public == True,            # Campaña es pública
                Campaign.created_by == consulted_by,   # Soy el creador de la campaña
                Campaign.id.in_(direct_camp_ids),      # Mi equipo tiene acceso directo
                Campaign.id.in_(inherited_camp_ids)    # Mi equipo tiene acceso al workspace
            )
        )

    @classmethod
    def get_all_active_with_rules(cls, session, campaign_id: int=None):
        query = session.query(cls.model).options(
            joinedload(cls.model.validation_rules)
        )

        query = cls._apply_tenant_filter(query)

        query = query.filter(cls.model.active == True)

        if campaign_id:
            query = query.filter(cls.model.campaign_id == campaign_id)

        return query.all()
    
    @classmethod
    def get_max_order(cls, session, campaign_id: int) -> int:
        """Obtiene el número de orden más alto en una campaña."""
        query = session.query(func.max(cls.model.order))
        
        query = cls._apply_tenant_filter(query)
        
        result = query.filter(cls.model.campaign_id == campaign_id).scalar()
        return result or 0

    @classmethod
    def order_exists(cls, session, campaign_id: int, order: int) -> bool:
        """Verifica si un número de orden ya está en uso en esa campaña."""
        query = session.query(cls.model.id)
        
        query = cls._apply_tenant_filter(query)
        
        return query.filter(
            cls.model.campaign_id == campaign_id,
            cls.model.order == order,
            cls.model.active == True
        ).first() is not None

