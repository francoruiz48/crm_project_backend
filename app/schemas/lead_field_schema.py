from app.schemas.base_schema import BaseCreate, BaseResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.schemas.validation_rule_schema import ValidationRuleResponse

class LeadFieldBase(BaseModel):
    name: Optional[str] = None
    field_type_code: Optional[str] = None
    required: bool = False
    default_value: Optional[str] = None
    is_primary: bool = False

class LeadFieldCreate(LeadFieldBase, BaseCreate):
    field_template_code: Optional[str] = None

class LeadFieldResponse(LeadFieldBase, BaseResponse):
    name: str
    field_type_code: str
    validation_rules: List[ValidationRuleResponse] = []
    
class LeadFieldTemplateResponse(BaseModel):
    code: str
    name: str
    field_type_code: str
    rules: List[Dict[str, Any]]