from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.audit.lead_activity_history import LeadActivityHistory
from app.schemas.audit.lead_activity_history_schema import LeadActivityHistoryResponse, LeadActivityHistoryDetailedResponse

class LeadActivityHistoryRepository(BaseRepository):
    model = LeadActivityHistory
    delete_strategy = DeleteStrategy.PROTECTED
    schema_out = LeadActivityHistoryResponse
    schema_out_detail = LeadActivityHistoryDetailedResponse