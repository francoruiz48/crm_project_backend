from app.services.base_service import BaseService
from app.db.repository.lead_field_section_repository import LeadFieldSectionRepository

class LeadFieldSectionService(BaseService):
    repository = LeadFieldSectionRepository
