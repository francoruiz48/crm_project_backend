from app.services.base_service import BaseService
from app.db.repository.lead_field_type_repository import LeadFieldTypeRepository

class LeadFieldTypeService(BaseService):
    repository = LeadFieldTypeRepository
