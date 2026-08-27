from app.schemas.base_schema import BaseCreate, BaseDetailedResponse, BaseResponse
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
    default_value: Optional[str] = Field(default=None, max_length=500)
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
    title_order: Optional[int] = Field(default=None, gt=0, le=2)
    subtitle_order: Optional[int] = Field(default=None, gt=0, le=2)


class LeadFieldCreate(LeadFieldBase, BaseCreate):
    # public_uuid de Campaign (Fase 3). El Response sigue con el int interno viejo (FK
    # embebida, deliberadamente sin migrar -- ver backend/AGENTS.md §18).
    campaign_id: str
    field_template_code: Optional[str] = Field(default=None, min_length=2, max_length=100)
    # public_uuid de Nomenclator/Campaign/LeadFieldSection/LeadField (Fase 3, ver
    # backend/AGENTS.md §18). El service los resuelve a id interno antes de usarlos.
    nomenclator_id: Optional[str] = Field(default=None)
    related_campaign_id: Optional[str] = Field(default=None)
    lead_field_section_id: Optional[str] = Field(default=None)
    mask_template_code: Optional[str] = Field(
        default=None,
        description="Código de máscara predefinida (Ej: DNI_ARG, MOBILE_AR)"
    )
    # Feature de nomencladores dependientes (ver docs/nomencladores.md): este
    # campo (SELECTOR/CHECKBOX) solo va a ofrecer ítems hijos del valor
    # elegido en el campo referenciado, que debe ser de la misma campaña.
    depends_on_field_id: Optional[str] = Field(default=None)

class LeadFieldUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=150)
    required: Optional[bool] = None
    default_value: Optional[str] = Field(default=None, max_length=500)
    is_primary: Optional[bool] = None
    input_mask: Optional[str] = Field(default=None, min_length=2, max_length=150)
    is_visible: Optional[bool] = None
    order: Optional[int] = Field(default=None, gt=0)
    calculation_expression: Optional[str] = Field(default=None, min_length=2, max_length=1000)
    configuration: Optional[Dict[str, Any]] = None
    # public_uuid de LeadFieldSection (Fase 3, ver backend/AGENTS.md §18).
    lead_field_section_id: Optional[str] = Field(default=None)
    title_order: Optional[int] = Field(default=None, gt=0, le=2)
    subtitle_order: Optional[int] = Field(default=None, gt=0, le=2)
    # No mandar el campo = no tocar la dependencia actual. Mandar explícitamente
    # `null` desvincula (gracias a exclude_unset=True en el repositorio, que sí
    # distingue "no vino" de "vino en null" — ver BaseRepository._normalize_data).
    # public_uuid de LeadField (Fase 3, ver backend/AGENTS.md §18).
    depends_on_field_id: Optional[str] = Field(default=None)

class LeadFieldResponse(LeadFieldBase, BaseResponse):
    field_template_name: Optional[str] = None
    field_type: Optional[LeadFieldTypeResponse] = None
    field_subtype: Optional[LeadFieldSubtypeResponse] = None
    lead_field_section: LeadFieldSectionResponse
    nomenclator_id: Optional[int] = None
    related_campaign_id: Optional[int] = None
    depends_on_field_id: Optional[int] = None
    organization_id : int

class LeadFieldLiteResponse(BaseModel, BaseResponse):
    name: str
    order: int
    field_type_code: Optional[str] = None
    field_subtype_code: Optional[str] = None
    title_order: Optional[int] = None
    subtitle_order: Optional[int] = None


class LeadFieldDetailedResponse(LeadFieldBase, BaseDetailedResponse):
    field_template_name: Optional[str] = None
    field_type: Optional[LeadFieldTypeResponse] = None
    field_subtype: Optional[LeadFieldSubtypeResponse] = None
    lead_field_section: LeadFieldSectionDetailedResponse
    validation_rules: List[ValidationRuleResponse] = []
    nomenclator: Optional[NomenclatorResponse] = None
    related_campaign: Optional[CampaignResponse] = None
    depends_on_field_id: Optional[int] = None
    # Fase 4: objeto anidado con el uuid real (ver backend/AGENTS.md §18), mismo patrón que
    # nomenclator/related_campaign de arriba. Usa LeadFieldLiteResponse (ya definida más abajo
    # en este módulo) para no traer validation_rules/nomenclator/etc. del campo padre.
    depends_on_field: Optional["LeadFieldLiteResponse"] = None
    organization_id : int
    
class LeadFieldOrderUpdate(BaseModel):
    # public_uuid de LeadField (Fase 3, ver backend/AGENTS.md §18); el service lo resuelve.
    field_id: str
    order: int = Field(gt=0)

class LeadFieldOrderList(BaseModel):
    # public_uuid de Campaign (Fase 3, ver backend/AGENTS.md §18); el service lo resuelve.
    campaign_id: str
    orders: List[LeadFieldOrderUpdate]