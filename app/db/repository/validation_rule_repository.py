
from app.db.repository.base_repository import BaseRepository
from app.models.lead_field import LeadField
from app.models.validation_rule import ValidationRule
from app.schemas.validation_rule_schema import ValidationRuleResponse
from sqlalchemy.orm import selectinload

class ValidationRuleRepository(BaseRepository):
    model = ValidationRule
    schema_out = ValidationRuleResponse

    relations = [
        selectinload(ValidationRule.field).selectinload(LeadField.field_type),
        selectinload(ValidationRule.related_field).selectinload(LeadField.field_type),
        selectinload(ValidationRule.rule_type)
    ]