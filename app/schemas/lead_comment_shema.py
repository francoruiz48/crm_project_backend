
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.lead_field_value_schema import LeadFieldValueCreate, LeadFieldValueDetailedResponse, LeadFieldValueResponse


class LeadCommentBase(BaseModel):
    content: str = Field(min_length=1, max_length=600)
    color : Optional[str] = Field(default=None)
    lead_id: int = Field(gt=0)

class LeadCommentCreate(LeadCommentBase, BaseCreate):
    pass

class LeadCommentUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=600)
    color : Optional[str] = Field(default=None)

class LeadCommentResponse(LeadCommentBase, BaseResponse):
    pass

class LeadCommentDetailedResponse(LeadCommentBase, BaseDetailedResponse):
    pass


