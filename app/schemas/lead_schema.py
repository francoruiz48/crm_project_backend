
from app.schemas.base_schema import BaseResponse, BaseCreate
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any
from app.schemas.lead_field_value_schema import LeadFieldValueCreate, LeadFieldValueResponse


class LeadBase(BaseModel):
    pass


class LeadCreate(LeadBase, BaseCreate):
    values: List[LeadFieldValueCreate]


class LeadResponse(LeadBase, BaseResponse):
    field_values: List[LeadFieldValueResponse] = Field(
        default_factory=list,
        exclude=True
    )

    @computed_field
    def fields(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": fv.field.name,
                "value": fv.value,
                "required": fv.field.required
            }
            for fv in self.field_values
        ]

