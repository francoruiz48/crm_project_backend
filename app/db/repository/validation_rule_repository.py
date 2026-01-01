from app.db.repository.base_repository import BaseRepository
from app.models.validation_rule import ValidationRule
from app.schemas.validation_rule_schema import ValidationRuleDetailedResponse, ValidationRuleResponse


class ValidationRuleRepository(BaseRepository):
    model = ValidationRule
    schema_out = ValidationRuleResponse
    schema_out_detail = ValidationRuleDetailedResponse

