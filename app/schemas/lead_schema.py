
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.lead_comment_shema import LeadCommentDetailedResponse
from app.schemas.lead_field_value_schema import LeadFieldValueCreate, LeadFieldValueDetailedResponse, LeadFieldValueResponse
from app.schemas.lead_state_schema import LeadStateDetailedResponse, LeadStateResponse


class LeadBase(BaseModel):
    campaign_id: int = Field(gt=0)
    assigned_to_user_id: Optional[int] = Field(default=None, gt=0)
    team_id: Optional[int] = Field(default=None, gt=0)

class LeadCreate(LeadBase, BaseCreate):
    values: List[LeadFieldValueCreate]

class LeadUpdate(BaseModel):
    values: Optional[List[LeadFieldValueCreate]] = None

class LeadResponse(LeadBase, BaseResponse):
    field_values: List[LeadFieldValueResponse] = Field(
        default_factory=list
    )
    organization_id : int
    current_state_id: int

class LeadDetailedResponse(LeadBase, BaseDetailResponse):
    field_values: List[LeadFieldValueDetailedResponse] = Field(
        default_factory=list
    )
    comments: List[LeadCommentDetailedResponse] = None
    organization_id : int
    current_state: LeadStateDetailedResponse
    current_state_id: int


