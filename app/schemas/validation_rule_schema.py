import datetime
from typing import Optional
from pydantic import BaseModel
from app.schemas.base_schema import BaseResponse, BaseCreate


class ValidationRuleBase(BaseModel):
    value: Optional[str] = None
    rule_type_code : str
    field_id : int
    related_field_id: Optional[int] = None


class ValidationRuleCreate(ValidationRuleBase, BaseCreate):
    pass


class ValidationRuleResponse(ValidationRuleBase, BaseResponse):
    pass
