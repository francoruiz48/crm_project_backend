from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.audit.system_audit_log import SystemAuditLog
from app.schemas.audit.system_audit_log_schema import SystemAuditLogResponse, SystemAuditLogDetailedResponse

class SystemAuditLogRepository(BaseRepository):
    model = SystemAuditLog
    delete_strategy = DeleteStrategy.PROTECTED
    schema_out = SystemAuditLogResponse
    schema_out_detail = SystemAuditLogDetailedResponse