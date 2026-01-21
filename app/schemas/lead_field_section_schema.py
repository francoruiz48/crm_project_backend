from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field


class LeadFieldSectionBase(BaseModel):
    name: str = Field(min_length=3, max_length=100)

class LeadFieldSectionCreate(LeadFieldSectionBase, BaseCreate):
    pass

class LeadFieldSectionResponse(LeadFieldSectionBase, BaseResponse):
    pass

class LeadFieldSectionDetailedResponse(LeadFieldSectionBase, BaseDetailResponse):
    pass


