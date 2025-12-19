
from app.schemas.base_schema import BaseResponse, BaseCreate
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any
from app.schemas.lead_field_value_schema import LeadFieldValueCreate, LeadFieldValueResponse


class LeadBase(BaseModel):
    campaign_id: int


class LeadCreate(LeadBase, BaseCreate):
    values: List[LeadFieldValueCreate]


class LeadResponse(LeadBase, BaseResponse):
    field_values: List[LeadFieldValueResponse] = Field(
        default_factory=list
    )


