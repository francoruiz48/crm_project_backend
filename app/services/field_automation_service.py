from app.services.base_service import BaseService
from app.db.repository.field_automation_repository import FieldAutomationRepository

class FieldAutomationService(BaseService):
    repository = FieldAutomationRepository
