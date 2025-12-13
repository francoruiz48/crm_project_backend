import datetime
from typing import Optional
from pydantic import BaseModel
from app.schemas.base_schema import BaseResponse, BaseCreate


class ValidationRuleBase(BaseModel):
    name: str
    expression: str
    error_message: str
    field_id : Optional[int] = None
    related_field_id: Optional[int] = None


class ValidationRuleCreate(ValidationRuleBase, BaseCreate):
    pass


class ValidationRuleResponse(ValidationRuleBase, BaseResponse):
    pass
