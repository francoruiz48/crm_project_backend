from datetime import datetime
from pydantic import BaseModel, computed_field, PrivateAttr
from typing import List, Dict, Any
from app.schemas.lead_field_value_schema import LeadFieldValueCreate, LeadFieldValueResponse


class LeadBase(BaseModel):
    pass  # en este modelo todavía no  hay campos fijos, los define dinámicamente el usuario


class LeadCreate(LeadBase):
    values: List[LeadFieldValueCreate]


class LeadResponse(LeadBase):
    id: int
    created_at: datetime
    updated_at: datetime
    _field_values: List[LeadFieldValueResponse] = PrivateAttr(default=[])

    @computed_field
    def fields(self) -> List[Dict[str, Any]]:
        """Devuelve [{name, value, required}]"""
        result = []
        for fv in self._field_values:
            result.append({
                "name": fv.field.name,
                "value": fv.value,
                "required": fv.field.required
            })
        return result

    model_config = {
        "from_attributes": True
    }
