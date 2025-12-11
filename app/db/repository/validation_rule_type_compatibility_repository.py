
from app.db.repository.base_repository import BaseRepository
from app.models.validation_rule_type_compatibility import ValidationRuleTypeCompatibility
from app.schemas.validation_rule_type_compatibility_schema import ValidationRuleTypeCompatibilityResponse


class ValidationRuleTypeCompabilityRepository(BaseRepository):
    model = ValidationRuleTypeCompatibility
    schema_out = ValidationRuleTypeCompatibilityResponse
