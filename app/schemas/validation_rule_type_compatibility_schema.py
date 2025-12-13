from app.schemas.base_schema import BaseResponse, BaseCreate
from pydantic import BaseModel, computed_field, PrivateAttr
from app.schemas.lead_field_type_schema import LeadFieldTypeResponse
from app.schemas.validation_rule_type_schema import ValidationRuleTypeResponse


class ValidationRuleTypeCompatibilityBase(BaseModel):
    is_compatible : bool
    validation_rule_type_code : str
    lead_field_type_code : str


class ValidationRuleTypeCompatibilityCreate(ValidationRuleTypeCompatibilityBase, BaseCreate):
    pass

class ValidationRuleTypeCompatibilityResponse(ValidationRuleTypeCompatibilityBase, BaseResponse):
    pass
