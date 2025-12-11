from app.schemas.base_schema import BaseResponse, BaseCreate
from pydantic import BaseModel, computed_field, PrivateAttr
from app.schemas.lead_field_type_schema import LeadFieldTypeResponse
from app.schemas.validation_rule_type_schema import ValidationRuleTypeResponse


class ValidationRuleTypeCompatibilityBase(BaseModel):
    is_compatible : bool


class ValidationRuleTypeCompatibilityCreate(ValidationRuleTypeCompatibilityBase, BaseCreate):
    validation_rule_type_code : str
    lead_field_type_code : str
    


class ValidationRuleTypeCompatibilityResponse(ValidationRuleTypeCompatibilityBase, BaseResponse):
    validation_rule_type : ValidationRuleTypeResponse
    lead_field_type : LeadFieldTypeResponse

    @computed_field
    def fields(self) -> dict:
        result = {
            "validation_rule_type": self.validation_rule_type.code,
            "lead_field_type": self.lead_field_type.code
        }
        return result
