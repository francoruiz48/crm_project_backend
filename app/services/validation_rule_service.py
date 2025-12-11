from app.db.repository.validation_rule_repository import ValidationRuleRepository
from app.services.base_service import BaseService


class ValidationRuleService(BaseService):
    repository = ValidationRuleRepository
