import datetime
from typing import Any, Dict, Optional, List
from app.schemas.base_schema import BaseResponse, BaseCreate
from pydantic import BaseModel, computed_field, PrivateAttr

from app.schemas.validation_rule_type_schema import ValidationRuleTypeResponse
from app.schemas.lead_field_schema import LeadFieldResponse


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


class ValidationRuleCreate(ValidationRuleBase, BaseCreate):
    
    field_id : int
    related_field_id: Optional[int] = None


class ValidationRuleResponse(ValidationRuleBase, BaseResponse):
    _field : LeadFieldResponse = PrivateAttr(default=None)
    _related_field : Optional[LeadFieldResponse] = PrivateAttr(default=None)

    @computed_field
    def fields(self) -> Dict[str, Any]:
        result = {
            "field": self._field.name if self._field else None,
            "related_field": self._related_field.name if self._related_field else None
        }
        return result
