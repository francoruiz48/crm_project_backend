from app.schemas.base_schema import BaseResponse, BaseCreate
from app.schemas.lead_field_schema import LeadFieldResponse
from pydantic import BaseModel
from typing import Optional


class LeadFieldValueBase(BaseModel):
    field_id: int
    value: Optional[str] = None


class LeadFieldValueCreate(LeadFieldValueBase, BaseCreate):
    pass


class LeadFieldValueResponse(LeadFieldValueBase, BaseResponse):
    lead_id: int
    field: Optional[LeadFieldResponse] = None

