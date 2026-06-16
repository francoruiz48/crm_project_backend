from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.validation_rule import ValidationRule
from app.schemas.validation_rule_schema import ValidationRuleDetailedResponse, ValidationRuleResponse


class ValidationRuleRepository(BaseRepository):
    model = ValidationRule
    delete_strategy = DeleteStrategy.HARD_DELETE_ALWAYS
    schema_out = ValidationRuleResponse
    schema_out_detail = ValidationRuleDetailedResponse

