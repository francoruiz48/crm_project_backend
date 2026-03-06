from typing import Optional
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field

class LeadFieldSubtypeBase(BaseModel):
    code: str
    description: str
    lead_field_type_code: str

class LeadFieldSubtypeCreate(LeadFieldSubtypeBase, BaseCreate):
    pass

class LeadFieldSubtypeUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=100)
    description: Optional[str] = Field(default=None, min_length=2, max_length=200)
    lead_field_type_code: Optional[str] = Field(default=None, min_length=2, max_length=100)

class LeadFieldSubtypeResponse(LeadFieldSubtypeBase, BaseResponse):
    pass

class LeadFieldSubtypeDetailedResponse(LeadFieldSubtypeBase, BaseDetailResponse):
    pass
