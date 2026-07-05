
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.lead_state_schema import LeadStateDetailedResponse

class LeadStateTransitionBase(BaseModel):
    lead_flow_id: int = Field(gt=0)
    from_state_id: int = Field(gt=0)
    to_state_id: int = Field(gt=0)

class LeadStateTransitionCreate(LeadStateTransitionBase, BaseCreate):
    pass

class LeadStateTransitionUpdate(BaseModel):
    from_state_id: Optional[int] = Field(default=None, gt=0)
    to_state_id: Optional[int] = Field(default=None, gt=0)

class LeadStateTransitionResponse(LeadStateTransitionBase, BaseResponse):
    pass

class LeadStateTransitionDetailedResponse(LeadStateTransitionBase, BaseDetailedResponse):
    from_state : Optional[LeadStateDetailedResponse]
    to_state : LeadStateDetailedResponse

class TransitionPair(BaseModel):
    from_state_id: int = Field(gt=0)
    to_state_id: int = Field(gt=0)

class LeadStateTransitionBulkCreate(BaseModel):
    lead_flow_id: int = Field(gt=0)
    transitions: List[TransitionPair] = Field(..., min_length=1)