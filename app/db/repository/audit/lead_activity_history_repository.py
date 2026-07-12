from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.audit.lead_activity_history import LeadActivityHistory
from app.models.lead import Lead
from app.schemas.audit.lead_activity_history_schema import LeadActivityHistoryResponse, LeadActivityHistoryDetailedResponse
from app.core.security import UserContext

class LeadActivityHistoryRepository(BaseRepository):
    model = LeadActivityHistory
    delete_strategy = DeleteStrategy.PROTECTED
    schema_out = LeadActivityHistoryResponse
    schema_out_detail = LeadActivityHistoryDetailedResponse

    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext = None):
        if user_context is None or user_context.user is None:
            return query

        if user_context.is_superuser:
            return query

        if user_context.organization_id is None:
            return query

        return query.join(Lead, LeadActivityHistory.lead_id == Lead.id).filter(
            Lead.organization_id == user_context.organization_id
        )