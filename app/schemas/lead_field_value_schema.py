from app.schemas.lead_field_schema import LeadFieldResponse
from pydantic import BaseModel
from typing import Optional


class LeadFieldValueBase(BaseModel):
    field_id: int
    value: Optional[str] = None


class LeadFieldValueCreate(LeadFieldValueBase):
    pass


class LeadFieldValueResponse(LeadFieldValueBase):
    id: int
    lead_id: int
    field: Optional[LeadFieldResponse] = None

    model_config = {
        "from_attributes": True
    }
