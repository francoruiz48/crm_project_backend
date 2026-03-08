from app.schemas.base_schema import BaseCreate, BaseDetailResponse, BaseResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from app.schemas.nomenclator_schema import NomenclatorResponse
from app.schemas.validation_rule_schema import ValidationRuleResponse
from app.schemas.lead_field_section_schema import LeadFieldSectionDetailedResponse, LeadFieldSectionResponse
from app.schemas.campaign_schema import CampaignResponse
from app.schemas.lead_field_subtype_schema import LeadFieldSubtypeResponse
from app.schemas.lead_field_type_schema import LeadFieldTypeResponse

class LeadFieldBase(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=150)
    required: bool = False
    default_value: Optional[str] = Field(default=None, min_length=2, max_length=500)
    is_primary: bool = False
    input_mask: Optional[str] = Field(default=None, min_length=2, max_length=150)
    is_visible: bool = True
    order: Optional[int] = Field(default=None, gt=0)
    campaign_id: int = Field(gt=0)
    calculation_expression: Optional[str] = Field(default=None, min_length=2, max_length=1000)
    configuration: Optional[Dict[str, Any]] = None
    field_type_code: Optional[str] = Field(default=None, min_length=2, max_length=100)
    field_subtype_code: Optional[str] = Field(default=None, min_length=2, max_length=100)
    field_template_code: Optional[str] = None

class LeadFieldCreate(LeadFieldBase, BaseCreate):
    field_template_code: Optional[str] = Field(default=None, min_length=2, max_length=100)
    nomenclator_id: Optional[int] = Field(default=None, gt=0)
    related_campaign_id: Optional[int] = Field(default=None, gt=0)
    lead_field_section_id: int = Field(default=None, gt=0)

class LeadFieldUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=150)
    required: Optional[bool] = None
    default_value: Optional[str] = Field(default=None, min_length=2, max_length=500)
    is_primary: Optional[bool] = None
    input_mask: Optional[str] = Field(default=None, min_length=2, max_length=150)
    is_visible: Optional[bool] = None
    order: Optional[int] = Field(default=None, gt=0)
    calculation_expression: Optional[str] = Field(default=None, min_length=2, max_length=1000)
    configuration: Optional[Dict[str, Any]] = None
    lead_field_section_id: Optional[int] = Field(default=None, gt=0)

class LeadFieldResponse(LeadFieldBase, BaseResponse):
    field_template_name: Optional[str] = None
    field_type: Optional[LeadFieldTypeResponse]
    field_subtype: Optional[LeadFieldSubtypeResponse]
    lead_field_section: LeadFieldSectionResponse
    nomenclator_id: Optional[int] = None
    related_campaign_id: Optional[int] = None
    organization_id : int
    

class LeadFieldDetailedResponse(LeadFieldBase, BaseDetailResponse):
    field_template_name: Optional[str] = None
    field_type: Optional[LeadFieldTypeResponse]
    field_subtype: Optional[LeadFieldSubtypeResponse]
    lead_field_section: LeadFieldSectionDetailedResponse
    validation_rules: List[ValidationRuleResponse] = []
    nomenclator: Optional[NomenclatorResponse]
    related_campaign: Optional[CampaignResponse]
    organization_id : int
    

