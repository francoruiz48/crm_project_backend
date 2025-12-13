from typing import Optional
from app.schemas.base_schema import BaseResponse, BaseCreate
from pydantic import BaseModel, computed_field, PrivateAttr


class ValidationRuleTypeBase(BaseModel):
    code : str
    description: Optional[str] = None
    lead_field_type_code: str


class ValidationRuleTypeCreate(ValidationRuleTypeBase, BaseCreate):
    pass


class ValidationRuleTypeResponse(ValidationRuleTypeBase, BaseResponse):
    pass
