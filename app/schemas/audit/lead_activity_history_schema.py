from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from app.schemas.base_schema import UserSimpleResponse

class LeadActivityHistoryResponse(BaseModel):
    id: int
    lead_id: Optional[int]
    activity_type: str
    details: Optional[Dict[str, Any]]
    created_at: datetime
    created_by: Optional[int]
    creator: Optional[UserSimpleResponse] = None

    class Config:
        from_attributes = True

class LeadActivityHistoryDetailedResponse(LeadActivityHistoryResponse):
    pass