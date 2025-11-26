from app.services.base_service import BaseService
from app.db.repository.lead_field_value_repository import LeadFieldValueRepository
from app.schemas.lead_field_value_schema import LeadFieldValueCreate


class LeadFieldValueService(BaseService):
    repository = LeadFieldValueRepository

    @classmethod
    def create_for_lead(cls, lead_id: int, values: list[LeadFieldValueCreate]):
        """Crea múltiples LeadFieldValue asociados a un lead."""
        created_values = []
        for value_data in values:
            data_dict = value_data.dict()
            data_dict["lead_id"] = lead_id
            created_value = cls.repository.create_simple(data_dict)
            created_values.append(created_value)
        return created_values
