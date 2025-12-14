from app.schemas.base_schema import BaseCreate, BaseResponse
from pydantic import BaseModel
from typing import Optional
from typing import List
from app.schemas.validation_rule_schema import ValidationRuleResponse


class LeadFieldBase(BaseModel):
    name: str
    field_type_code: str
    required: bool = False
    default_value: Optional[str] = None
    is_primary: bool = False


class LeadFieldCreate(LeadFieldBase, BaseCreate):
    pass


class LeadFieldResponse(LeadFieldBase, BaseResponse):
    validation_rules: List[ValidationRuleResponse] = []
    
