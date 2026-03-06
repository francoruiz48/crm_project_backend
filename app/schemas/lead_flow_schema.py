
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.campaign_schema import CampaignDetailedResponse
from app.schemas.lead_state_schema import LeadStateDetailedResponse
from app.schemas.lead_state_transition_schema import LeadStateTransitionDetailedResponse

class LeadFlowBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)

class LeadFlowCreate(LeadFlowBase, BaseCreate):
    pass

class LeadFlowUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)

class LeadFlowResponse(LeadFlowBase, BaseResponse):
    organization_id: int = Field(gt=0)

class LeadFlowDetailedResponse(LeadFlowBase, BaseDetailResponse):
    organization_id: int = Field(gt=0)
    transitions: List[LeadStateTransitionDetailedResponse] = [] 
    campaigns: List[CampaignDetailedResponse] = []
    states: List[LeadStateDetailedResponse] = []

    