from typing import Optional, Union
from pydantic import BaseModel, Field
from app.schemas.base_schema import BaseCreate, BaseResponse
from app.schemas.lead_field_schema import LeadFieldLiteResponse

class WebFormFieldBase(BaseModel):
    lead_field_id: int = Field(gt=0, description="El ID del campo real en el CRM")
    order: int = Field(default=1, gt=0)
    custom_label: Optional[str] = Field(default=None, max_length=150, description="Etiqueta pública que pisa el nombre original")
    custom_placeholder: Optional[str] = Field(default=None, max_length=150)
    is_required: bool = False
    hidden_value: Optional[str] = Field(default=None, max_length=500, description="Si tiene valor, se oculta en el front y se manda este string")

class WebFormFieldCreate(WebFormFieldBase, BaseCreate):
    # Override: a diferencia de WebFormFieldBase.lead_field_id (int, lo que sigue esperando el
    # Response), acá acepta también el public_uuid del LeadField (Fase 3, nunca migrado en este
    # módulo -- ver backend/AGENTS.md §18-undecies). Se resuelve en
    # WebFormService._resolve_lead_field_ids antes de tocar la base de datos.
    lead_field_id: Union[int, str] = Field(description="public_uuid (o, para callers internos, id interno) del LeadField real en el CRM")

class WebFormFieldUpdate(BaseModel):
    order: Optional[int] = Field(default=None, gt=0)
    custom_label: Optional[str] = Field(default=None, max_length=150)
    custom_placeholder: Optional[str] = Field(default=None, max_length=150)
    is_required: Optional[bool] = None
    hidden_value: Optional[str] = Field(default=None, max_length=500)

class WebFormFieldResponse(WebFormFieldBase, BaseResponse):
    web_form_id: int
    lead_field: Optional[LeadFieldLiteResponse] = None