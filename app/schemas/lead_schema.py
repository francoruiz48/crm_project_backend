
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.lead_comment_shema import LeadCommentDetailedResponse
from app.schemas.lead_field_value_schema import LeadFieldValueCreate, LeadFieldValueDetailedResponse, LeadFieldValueResponse
from app.schemas.lead_state_schema import LeadStateDetailedResponse, LeadStateResponse
from app.schemas.tag_schema import TagResponse


class LeadBase(BaseModel):
    campaign_id: int = Field(gt=0)
    assigned_to_user_id: Optional[int] = Field(default=None, gt=0)
    team_id: Optional[int] = Field(default=None, gt=0)
    contact_state_id: Optional[int] = Field(default=None, gt=0)
    

class LeadCreate(LeadBase, BaseCreate):
    values: List[LeadFieldValueCreate]
    tag_ids: Optional[List[int]] = Field(default_factory=list)

class LeadUpdate(BaseModel):
    values: Optional[List[LeadFieldValueCreate]] = None
    contact_state_id: Optional[int] = Field(default=None, gt=0)
    tag_ids: Optional[List[int]] = Field(default_factory=list)

class LeadResponse(LeadBase, BaseResponse):
    field_values: List[LeadFieldValueResponse] = Field(
        default_factory=list
    )
    organization_id : int
    current_state_id: int
    tags: List[TagResponse] = Field(default_factory=list)

class LeadLiteResponse(LeadBase, BaseResponse):
    organization_id : int
    current_state_id: int

class LeadDetailedResponse(LeadBase, BaseDetailedResponse):
    field_values: List[LeadFieldValueDetailedResponse] = Field(
        default_factory=list
    )
    tags: List[TagResponse] = Field(default_factory=list)
    comments: List[LeadCommentDetailedResponse] = None
    organization_id : int
    current_state: LeadStateDetailedResponse
    current_state_id: int


