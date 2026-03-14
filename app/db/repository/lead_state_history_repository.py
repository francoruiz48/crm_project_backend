
from app.db.repository.base_repository import BaseRepository
from app.models.lead_state_history import LeadStateHistory
from app.schemas.lead_state_history_schema import LeadStateHistoryDetailedResponse, LeadStateHistoryResponse

class LeadStateHistoryRepository(BaseRepository):
    model = LeadStateHistory
    schema_out = LeadStateHistoryResponse
    schema_out_detail = LeadStateHistoryDetailedResponse
