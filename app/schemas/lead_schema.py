
from app.schemas.base_schema import BaseResponse, BaseCreate
from pydantic import BaseModel, computed_field, PrivateAttr
from typing import List, Dict, Any
from app.schemas.lead_field_value_schema import LeadFieldValueCreate, LeadFieldValueResponse


class LeadBase(BaseModel):
    pass


class LeadCreate(LeadBase, BaseCreate):
    values: List[LeadFieldValueCreate]


class LeadResponse(LeadBase, BaseResponse):
    _field_values: List[LeadFieldValueResponse] = PrivateAttr(default=[])

    @computed_field
    def fields(self) -> List[Dict[str, Any]]:
        result = []
        for fv in self._field_values:
            result.append({
                "name": fv.field.name,
                "value": fv.value,
                "required": fv.field.required
            })
        return result

