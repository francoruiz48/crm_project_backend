from app.db.repository.base_repository import BaseRepository
from app.models.audit.lead_activity_history import LeadActivityHistory
from app.schemas.audit.lead_activity_history_schema import LeadActivityHistoryResponse, LeadActivityHistoryDetailedResponse

class LeadActivityHistoryRepository(BaseRepository):
    model = LeadActivityHistory
    schema_out = LeadActivityHistoryResponse
    schema_out_detail = LeadActivityHistoryDetailedResponse