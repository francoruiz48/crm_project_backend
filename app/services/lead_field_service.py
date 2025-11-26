from app.services.base_service import BaseService
from app.db.repository.lead_field_repository import LeadFieldRepository


class LeadFieldService(BaseService):
    repository = LeadFieldRepository
