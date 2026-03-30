from app.services.base_service import BaseService
from app.db.repository.audit.system_audit_log_repository import SystemAuditLogRepository

class SystemAuditLogService(BaseService):
    repository = SystemAuditLogRepository
    
    @classmethod
    def create(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")

    @classmethod
    def update(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")

    @classmethod
    def delete(cls, *args, **kwargs):
        raise NotImplementedError("Los logs de auditoría son inmutables.")