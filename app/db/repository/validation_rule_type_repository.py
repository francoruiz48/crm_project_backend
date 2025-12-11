
from app.db.repository.base_repository import BaseRepository
from app.models.validation_rule_type import ValidationRuleType
from app.schemas.validation_rule_type_schema import ValidationRuleTypeResponse

class ValidationRuleTypeRepository(BaseRepository):
    model = ValidationRuleType
    schema_out = ValidationRuleTypeResponse
