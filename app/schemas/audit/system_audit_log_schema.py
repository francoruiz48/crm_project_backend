from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class SystemAuditLogResponse(BaseModel):
    id: int
    organization_id: Optional[int]
    entity_type: str
    entity_id: int
    action: str
    changes: Optional[Dict[str, Any]]
    created_at: datetime
    created_by: Optional[int]

    class Config:
        from_attributes = True

class SystemAuditLogDetailedResponse(SystemAuditLogResponse):
    pass


