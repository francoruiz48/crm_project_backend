from app.schemas.base_schema import BaseCreate, BaseResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.schemas.campaign_schema import CampaignResponse
from app.schemas.nomenclator_schema import NomenclatorResponse
from app.schemas.validation_rule_schema import ValidationRuleResponse

class LeadFieldBase(BaseModel):
    name: Optional[str] = None
    field_type_code: Optional[str] = None
    required: bool = False
    default_value: Optional[str] = None
    is_primary: bool = False

class LeadFieldCreate(LeadFieldBase, BaseCreate):
    field_template_code: Optional[str] = None
    nomenclator_id: Optional[int] = None
    campaign_id: int

class LeadFieldResponse(LeadFieldBase, BaseResponse):
    name: str
    field_type_code: str
    validation_rules: List[ValidationRuleResponse] = []
    nomenclator: Optional[NomenclatorResponse]
    campaign: CampaignResponse


class LeadFieldTemplateResponse(BaseModel):
    code: str
    name: str
    field_type_code: str
    rules: List[Dict[str, Any]]