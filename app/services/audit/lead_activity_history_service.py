from app.services.base_service import BaseService
from app.db.repository.audit.lead_activity_history_repository import LeadActivityHistoryRepository

class LeadActivityHistoryService(BaseService):
    repository = LeadActivityHistoryRepository
    
    @classmethod
    def create(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")

    @classmethod
    def update(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")

    @classmethod
    def delete(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")