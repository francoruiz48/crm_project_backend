from app.db.repository.base_repository import BaseRepository
from app.models.lead_field import LeadField
from app.models.validation_rule import ValidationRule
from app.models.validation_rule_type import ValidationRuleType
from app.schemas.validation_rule_schema import ValidationRuleResponse


class ValidationRuleRepository(BaseRepository):
    model = ValidationRule
    schema_out = ValidationRuleResponse

    @classmethod
    def exists_rule_for_field(cls, session, field_id: int, rule_type_code: str, exclude_id: int = None) -> bool:
        """
        Verifica si ya existe una regla del mismo tipo para el mismo campo.
        exclude_id: Se usa en updates para excluir la regla actual de la búsqueda.
        """
        query = session.query(cls.model).filter(
            cls.model.field_id == field_id,
            cls.model.rule_type_code == rule_type_code
        )
        
        if exclude_id:
            query = query.filter(cls.model.id != exclude_id)
            
        return session.query(query.exists()).scalar()

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
