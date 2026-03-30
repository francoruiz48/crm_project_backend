from typing import Optional

from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field

from app.schemas.lead_field_subtype_schema import LeadFieldSubtypeResponse

class LeadFieldTypeBase(BaseModel):
    code: str = Field(..., min_length=2, max_length=100)
    description: str = Field(..., min_length=2, max_length=200)

class LeadFieldTypeCreate(LeadFieldTypeBase, BaseCreate):
    pass

class LeadFieldTypeUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=100)
    description: Optional[str] = Field(default=None, min_length=2, max_length=200)

class LeadFieldTypeResponse(LeadFieldTypeBase, BaseResponse):
    pass

class LeadFieldTypeDetailedResponse(LeadFieldTypeBase, BaseDetailResponse):
    subtypes: list[LeadFieldSubtypeResponse] = []
