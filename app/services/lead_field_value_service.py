from app.services.base_service import BaseService
from app.db.repository.lead_field_value_repository import LeadFieldValueRepository
from app.schemas.lead_field_value_schema import LeadFieldValueCreate


class LeadFieldValueService(BaseService):
    repository = LeadFieldValueRepository

    @classmethod
    def create_for_lead(cls, lead_id: int, values: list[LeadFieldValueCreate], created_by=None):
        created = []

        for value_data in values:
            data = value_data.dict()
            data["lead_id"] = lead_id
            created.append(cls.repository.create(data, created_by))

        return created
