from sqlalchemy import or_, and_
from app.core.constans import DeleteStrategy
from app.db.repository.base_repository import BaseRepository
from app.models.lead_view import LeadView
from app.models.team_member import TeamMember
from app.schemas.lead_view_schema import LeadViewCreate, LeadViewResponse, LeadViewDetailedResponse
from app.core.security import UserContext

class LeadViewRepository(BaseRepository):
    model = LeadView
    delete_strategy = DeleteStrategy.HARD_DELETE_ALWAYS
    schema_in = LeadViewCreate
    schema_out = LeadViewResponse
    schema_out_detail = LeadViewDetailedResponse

    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext = None):

        if user_context is None or user_context.user is None:
            return query
        
        consulted_by = user_context.user.id

        if user_context.is_superuser or user_context.is_owner:
            return query

        # Obtenemos los equipos del usuario
        user_team_ids = session.query(TeamMember.team_id).filter(
            TeamMember.user_id == consulted_by
        ).subquery()

        security_condition = or_(
            cls.model.visibility == "PUBLIC",
            and_(cls.model.visibility == "PRIVATE", cls.model.created_by == consulted_by),
            and_(cls.model.visibility == "TEAM", cls.model.team_id.in_(user_team_ids))
        )

        return query.filter(security_condition)