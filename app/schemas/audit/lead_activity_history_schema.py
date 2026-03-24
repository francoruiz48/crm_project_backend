from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class LeadActivityHistoryResponse(BaseModel):
    id: int
    lead_id: Optional[int]
    activity_type: str
    details: Optional[Dict[str, Any]]
    created_at: datetime
    created_by: Optional[int]

    class Config:
        from_attributes = True

class LeadActivityHistoryDetailedResponse(LeadActivityHistoryResponse):
    pass