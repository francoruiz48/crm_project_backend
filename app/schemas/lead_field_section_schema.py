from typing import Optional
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field


class LeadFieldSectionBase(BaseModel):
    name: str = Field(min_length=3, max_length=100)

class LeadFieldSectionCreate(LeadFieldSectionBase, BaseCreate):
    pass

class LeadFieldSectionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)

class LeadFieldSectionResponse(LeadFieldSectionBase, BaseResponse):
    organization_id: int

class LeadFieldSectionDetailedResponse(LeadFieldSectionBase, BaseDetailedResponse):
    organization_id: int


