from app.services.base_service import BaseService
from app.db.repository.lead_field_value_repository import LeadFieldValueRepository

class LeadFieldValueService(BaseService):
    repository = LeadFieldValueRepository
