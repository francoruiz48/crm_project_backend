from app.schemas.base_schema import BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field
from typing import Optional
from app.schemas.lead_field_type_schema import LeadFieldTypeResponse


class LeadFieldBase(BaseModel):
    name: str
    field_type_code: str
    required: bool = False
    default_value: Optional[str] = None
    is_primary: bool = False


class LeadFieldCreate(LeadFieldBase, BaseCreate):
    pass


class LeadFieldResponse(LeadFieldBase, BaseResponse):
    pass
    
