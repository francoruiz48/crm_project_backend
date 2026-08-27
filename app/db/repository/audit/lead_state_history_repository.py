
from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.audit.lead_state_history import LeadStateHistory
from app.models.lead import Lead
from app.schemas.audit.lead_state_history_schema import LeadStateHistoryDetailedResponse, LeadStateHistoryResponse
from app.core.security import UserContext

class LeadStateHistoryRepository(BaseRepository):
    model = LeadStateHistory
    delete_strategy = DeleteStrategy.PROTECTED
    schema_out = LeadStateHistoryResponse
    schema_out_detail = LeadStateHistoryDetailedResponse

    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext = None):
        if user_context is None or user_context.user is None:
            return query

        if user_context.is_superuser:
            return query

        if user_context.organization_id is None:
            return query

        return query.join(Lead, LeadStateHistory.lead_id == Lead.id).filter(
            Lead.organization_id == user_context.organization_id
        )
