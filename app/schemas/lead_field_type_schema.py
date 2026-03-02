from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel

from app.schemas.lead_field_subtype_schema import LeadFieldSubtypeResponse

class LeadFieldTypeBase(BaseModel):
    code: str
    description: str


class LeadFieldTypeCreate(LeadFieldTypeBase, BaseCreate):
    pass


class LeadFieldTypeResponse(LeadFieldTypeBase, BaseResponse):
    pass

class LeadFieldTypeDetailedResponse(LeadFieldTypeBase, BaseDetailResponse):
    subtypes: list[LeadFieldSubtypeResponse] = []
