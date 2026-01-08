from app.schemas.base_schema import BaseCreate, BaseDetailResponse, BaseResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.schemas.nomenclator_schema import NomenclatorResponse
from app.schemas.validation_rule_schema import ValidationRuleResponse
from app.schemas.lead_field_section_schema import LeadFieldSectionDetailedResponse, LeadFieldSectionResponse

class LeadFieldBase(BaseModel):
    name: Optional[str] = None
    field_type_code: Optional[str] = None
    field_subtype_code: Optional[str] = None
    required: bool = False
    default_value: Optional[str] = None
    is_primary: bool = False
    is_primary: bool = False
    input_mask: Optional[str] = None
    field_template_code: Optional[str] = None
    is_visible: bool = True
    order: int
    campaign_id: int

class LeadFieldCreate(LeadFieldBase, BaseCreate):
    field_template_code: Optional[str] = None
    nomenclator_id: Optional[int] = None
    lead_field_section_id: int = None

class LeadFieldResponse(LeadFieldBase, BaseResponse):
    nomenclator_id: Optional[int] = None
    lead_field_section: LeadFieldSectionResponse

class LeadFieldDetailedResponse(LeadFieldBase, BaseDetailResponse):
    validation_rules: List[ValidationRuleResponse] = []
    nomenclator: Optional[NomenclatorResponse]
    lead_field_section: LeadFieldSectionDetailedResponse

class LeadFieldTemplateResponse(BaseModel):
    code: str
    name: str
    field_type_code: str
    rules: List[Dict[str, Any]]