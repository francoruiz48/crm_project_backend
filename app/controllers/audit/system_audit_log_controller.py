from app.controllers.base_controller import BaseController
from app.services.audit.system_audit_log_service import SystemAuditLogService
from app.schemas.audit.system_audit_log_schema import SystemAuditLogResponse, SystemAuditLogDetailedResponse
from app.core.constans import READ_ONLY

class SystemAuditLogController(BaseController):
    router_prefix = "/audit-logs"
    service = SystemAuditLogService
    schema_out = SystemAuditLogResponse
    schema_out_detail = SystemAuditLogDetailedResponse
    
    enabled_methods = READ_ONLY

router = SystemAuditLogController.get_router()