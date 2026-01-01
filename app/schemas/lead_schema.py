
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any
from app.schemas.lead_field_value_schema import LeadFieldValueCreate, LeadFieldValueDetailedResponse, LeadFieldValueResponse


class LeadBase(BaseModel):
    campaign_id: int


class LeadCreate(LeadBase, BaseCreate):
    values: List[LeadFieldValueCreate]


class LeadResponse(LeadBase, BaseResponse):
    field_values: List[LeadFieldValueResponse] = Field(
        default_factory=list
    )

class LeadDetailedResponse(LeadBase, BaseDetailResponse):
    field_values: List[LeadFieldValueDetailedResponse] = Field(
        default_factory=list
    )


