from fastapi import HTTPException
from app.services.base_service import BaseService
from app.db.repository.campaign_repository import CampaignRepository
from fastapi import HTTPException, status
from app.core.exceptions.exceptions import ValidationError
from app.models.nomenclator import Nomenclator
from app.services.base_service import BaseService
from app.core.templates.field_templates import STANDARD_FIELD_TEMPLATES
from app.services.nomenclator_service import NomenclatorService
from app.services.validation_rule_service import ValidationRuleService
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.repository.lead_repository import LeadRepository
from app.db.repository.lead_field_value_repository import LeadFieldValueRepository
from app.models.lead_field_type import LeadFieldType
from app.core.constans import DEFAULT_PAGE_SIZE, NOMENCLATOR_FIELD_TYPES
from app.models.lead_field_value import LeadFieldValue
from app.core.error_messages import SUCCESS_UPDATE
from app.models.lead_field import LeadField 

class CampaignService(BaseService):
    repository = CampaignRepository

    @classmethod
    def create(cls, obj_in, created_by=None):
        def do_create(uow):
            existing = cls.repository.get_all(
                session=uow.session, 
                name=obj_in.name, 
                workspace_id=obj_in.workspace_id,
                only_active=True
            )
            
            if existing:
                raise ValidationError(
                    f"Ya existe una campaña llamada '{obj_in.name}' en este espacio de trabajo.", 
                    field="name"
                )

            # 2. Crear
            return cls.repository.create(uow.session, obj_in, created_by)

        return cls._execute(action="Crear Campaña", func=do_create)