from app.services.base_service import BaseService
from app.db.repository.lead_field_subtype_repository import LeadFieldSubtypeRepository

class LeadFieldSubtypeService(BaseService):
    repository = LeadFieldSubtypeRepository
