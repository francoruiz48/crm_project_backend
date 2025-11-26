from app.services.base_service import BaseService
from app.db.repository.lead_repository import LeadRepository
from app.services.lead_field_value_service import LeadFieldValueService


class LeadService(BaseService):
    repository = LeadRepository

    @classmethod
    def create_empty_lead(cls):
        """Crea un lead sin valores asociados (solo ID y timestamps)."""
        lead_data = {}  # sin campos dinámicos
        lead = cls.repository.create_empty(lead_data)
        return lead

    @classmethod
    def create(cls, obj_in):
        lead = cls.create_empty_lead()
        values = obj_in.values if isinstance(obj_in.values, list) else [obj_in.values]
        LeadFieldValueService.create_for_lead(lead.id, values)
        return cls.get_by_id(lead.id)
