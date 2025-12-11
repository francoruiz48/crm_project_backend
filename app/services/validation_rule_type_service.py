from app.db.repository.validation_rule_type_repository import ValidationRuleTypeRepository
from app.services.base_service import BaseService


class ValidationRuleTypeService(BaseService):
    repository = ValidationRuleTypeRepository
