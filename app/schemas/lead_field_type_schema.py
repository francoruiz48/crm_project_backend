from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel

class LeadFieldTypeBase(BaseModel):
    code: str
    description: str


class LeadFieldTypeCreate(LeadFieldTypeBase, BaseCreate):
    pass


class LeadFieldTypeResponse(LeadFieldTypeBase, BaseResponse):
    pass

class LeadFieldTypeDetailedResponse(LeadFieldTypeBase, BaseDetailResponse):
    pass
