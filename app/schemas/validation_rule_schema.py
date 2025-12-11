import datetime
from typing import Any, Dict, Optional, List
from app.schemas.base_schema import BaseResponse, BaseCreate
from pydantic import BaseModel, computed_field, PrivateAttr

from app.schemas.validation_rule_type_schema import ValidationRuleTypeResponse
from app.schemas.lead_field_schema import LeadFieldResponse


class ValidationRuleBase(BaseModel):
    name: str
    static_value: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    regex_pattern: Optional[str] = None
    date_from: Optional[datetime.date] = None
    date_to: Optional[datetime.date] = None


class ValidationRuleCreate(ValidationRuleBase, BaseCreate):
    rule_type_id : int
    field_id : int
    related_field_id: Optional[int] = None


class ValidationRuleResponse(ValidationRuleBase, BaseResponse):
    rule_type : ValidationRuleTypeResponse
    field : LeadFieldResponse
    related_field : Optional[LeadFieldResponse] = None

    @computed_field
    def fields(self) -> Dict[str, Any]:
        result = {
            "rule_type": self.rule_type.code,
            "field": self.field.name,
            "related_field": self.related_field.name if self.related_field else ""
        }
        return result
