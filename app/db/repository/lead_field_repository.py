from app.db.repository.base_repository import BaseRepository
from app.models.lead_field import LeadField
from app.models.validation_rule import ValidationRule
from app.schemas.lead_field_schema import LeadFieldResponse
from sqlalchemy.orm import joinedload

class LeadFieldRepository(BaseRepository):
    model = LeadField
    schema_out = LeadFieldResponse

    relationships = [
        (LeadField.field_type,),
        (LeadField.validation_rules,),
        (LeadField.validation_rules_related,),
    ]

    @classmethod
    def get_all_active_with_rules(cls, session):
        """
        Trae todos los campos activos con sus reglas y tipos de reglas cargados.
        Corrección: Se usan atributos de clase en lugar de strings en joinedload.
        """
        return session.query(cls.model).options(
            # 1. Cargamos la relación 'validation_rules' desde LeadField
            # 2. Anidamos la carga de 'rule_type' usando la clase ValidationRule explícita
            joinedload(cls.model.validation_rules)
        ).filter(cls.model.active == True).all()
