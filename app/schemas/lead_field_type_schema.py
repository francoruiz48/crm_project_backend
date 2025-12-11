from app.schemas.base_schema import BaseResponse, BaseCreate
from pydantic import BaseModel

class LeadFieldTypeBase(BaseModel):
    code: str
    description: str


class LeadFieldTypeCreate(LeadFieldTypeBase, BaseCreate):
    pass


class LeadFieldTypeResponse(LeadFieldTypeBase, BaseResponse):
    pass
