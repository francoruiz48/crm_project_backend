
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field
from typing import Optional
from app.schemas.lead_state_schema import LeadStateDetailedResponse

class LeadStateHistoryBase(BaseModel):
    lead_id: int = Field(gt=0)
    from_state_id: Optional[int] = Field(default=None, gt=0)
    to_state_id: int = Field(gt=0)
    notes: Optional[str] = Field(default=None, max_length=1000) # Motivo del cambio

class LeadStateHistoryResponse(LeadStateHistoryBase, BaseResponse):
    pass

class LeadStateHistoryDetailedResponse(LeadStateHistoryBase, BaseDetailedResponse):
    from_state : Optional[LeadStateDetailedResponse] = None
    to_state : LeadStateDetailedResponse

    