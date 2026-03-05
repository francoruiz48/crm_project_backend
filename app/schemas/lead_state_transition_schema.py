
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.lead_state_schema import LeadStateDetailedResponse

class LeadStateTransitionBase(BaseModel):
    campaign_id: int = Field(gt=0)
    from_state_id: Optional[int] = Field(default=None, gt=0)
    to_state_id: int = Field(gt=0)

class LeadStateTransitionCreate(LeadStateTransitionBase, BaseCreate):
    pass

class LeadStateTransitionResponse(LeadStateTransitionBase, BaseResponse):
    pass

class LeadStateTransitionDetailedResponse(LeadStateTransitionBase, BaseDetailResponse):
    from_state : LeadStateDetailedResponse
    to_state : LeadStateDetailedResponse

