from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel

class LeadFieldSubtypeBase(BaseModel):
    code: str
    description: str
    lead_field_type_code: str

class LeadFieldSubtypeCreate(LeadFieldSubtypeBase, BaseCreate):
    pass


class LeadFieldSubtypeResponse(LeadFieldSubtypeBase, BaseResponse):
    pass

class LeadFieldSubtypeDetailedResponse(LeadFieldSubtypeBase, BaseDetailResponse):
    pass
