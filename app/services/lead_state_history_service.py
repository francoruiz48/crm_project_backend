from app.services.base_service import BaseService
from app.db.repository.lead_state_history_repository import LeadStateHistoryRepository

class LeadStateHistoryService(BaseService):
    repository = LeadStateHistoryRepository()