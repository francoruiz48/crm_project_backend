from app.services.base_service import BaseService
from app.db.repository.lead_repository import LeadRepository
from app.services.lead_field_value_service import LeadFieldValueService


class LeadService(BaseService):
    repository = LeadRepository

    @classmethod
    def create(cls, obj_in):
        lead = cls.repository.create()
        cls.repository.upsert_values(lead.id, obj_in.values)
        return cls.get_by_id(lead.id)
    
    @classmethod
    def update(cls, obj_id: int, obj_in):
        cls.repository.upsert_values(obj_id, obj_in.values)
        return cls.get_by_id(obj_id)
