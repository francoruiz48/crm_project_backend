from pydantic import BaseModel
from typing import Optional
from app.schemas.lead_field_type_schema import LeadFieldTypeResponse


class LeadFieldBase(BaseModel):
    name: str
    field_type_id: int
    required: bool = False
    default_value: Optional[str] = None


class LeadFieldCreate(LeadFieldBase):
    pass


class LeadFieldResponse(LeadFieldBase):
    id: int
    field_type: Optional[LeadFieldTypeResponse] = None  # relación

    model_config = {
        "from_attributes": True
    }
