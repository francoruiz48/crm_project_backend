from typing import Optional
from app.services.base_service import BaseService
from app.db.repository.audit.lead_activity_history_repository import LeadActivityHistoryRepository

class LeadActivityHistoryService(BaseService):
    repository = LeadActivityHistoryRepository

    @classmethod
    def _resolve_id(cls, session, obj_uuid: str) -> Optional[int]:
        """
        LeadActivityHistory no tiene public_uuid (log de auditoría solo-inserción,
        nunca heredó BaseModelDB) -- BaseService._resolve_id() genérico intenta
        resolver por public_uuid, columna que este modelo no tiene, y rompería con
        AttributeError en GET /lead-activity-histories/{obj_id}. Acá el "id" que
        llega en la URL ya es el id interno.
        """
        try:
            return int(obj_uuid)
        except (TypeError, ValueError):
            return None

    @classmethod
    def create(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")

    @classmethod
    def update(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")

    @classmethod
    def delete(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")