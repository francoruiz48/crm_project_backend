from app.services.base_service import BaseService
from app.db.repository.audit.lead_state_history_repository import LeadStateHistoryRepository

class LeadStateHistoryService(BaseService):
    repository = LeadStateHistoryRepository()

    @classmethod
    def create(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")

    @classmethod
    def update(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")

    @classmethod
    def delete(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")