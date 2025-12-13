import datetime
from typing import Optional
from pydantic import BaseModel
from app.schemas.base_schema import BaseResponse, BaseCreate


class ValidationRuleBase(BaseModel):
    static_value: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    regex_pattern: Optional[str] = None
    date_from: Optional[datetime.date] = None
    date_to: Optional[datetime.date] = None
    rule_type_code : str
    field_id : int
    related_field_id: Optional[int] = None


class ValidationRuleCreate(ValidationRuleBase, BaseCreate):
    pass


class ValidationRuleResponse(ValidationRuleBase, BaseResponse):
    pass
