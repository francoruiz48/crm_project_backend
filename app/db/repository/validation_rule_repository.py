from app.db.repository.base_repository import BaseRepository
from app.models.lead_field import LeadField
from app.models.validation_rule import ValidationRule
from app.models.validation_rule_type import ValidationRuleType
from app.schemas.validation_rule_schema import ValidationRuleResponse


class ValidationRuleRepository(BaseRepository):
    model = ValidationRule
    schema_out = ValidationRuleResponse

    @classmethod
    def is_rule_type_compatible_with_field(cls, session, rule_type_code: str, field_id: int) -> bool:
        """
        Verifica compatibilidad cruzando ValidationRuleType y LeadField.
        """
        query = session.query(ValidationRuleType).join(
            LeadField,
            ValidationRuleType.lead_field_type_code == LeadField.field_type_code
        ).filter(
            ValidationRuleType.code == rule_type_code,
            LeadField.id == field_id
        )

        return session.query(query.exists()).scalar()
