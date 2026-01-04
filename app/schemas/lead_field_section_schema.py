from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel


class LeadFieldSectionBase(BaseModel):
    name: str

class LeadFieldSectionCreate(LeadFieldSectionBase, BaseCreate):
    pass

class LeadFieldSectionResponse(LeadFieldSectionBase, BaseResponse):
    pass

class LeadFieldSectionDetailedResponse(LeadFieldSectionBase, BaseDetailResponse):
    pass


