from typing import List, Optional, Union
from pydantic import BaseModel, Field
from app.schemas.base_schema import BaseCreate, BaseResponse
from app.schemas.lead_field_schema import LeadFieldLiteResponse
from app.schemas.nomenclator_item_schema import NomenclatorItemLiteResponse

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
    # Gap real encontrado 2026-08-17 (al diseñar el frontend público): LeadFieldLiteResponse no
    # trae el nomenclador, así que un campo SELECTOR/CHECKBOX en un formulario público no tenía
    # forma de mostrar sus opciones -- GET /public/forms/{uuid} es el único endpoint que puede
    # consumir el iframe (sin auth), y /nomenclator_items/ requiere login. Se resuelve poblando
    # este campo (solo cuando aplica) en WebFormService.get_public_form_by_uuid, como atributo
    # transitorio sobre el objeto ORM (no es una columna ni relación real de WebFormField).
    # None para cualquier otro tipo de campo, o si el nomenclador no tiene ítems activos.
    nomenclator_items: Optional[List[NomenclatorItemLiteResponse]] = None
    # OJO (2026-08-18): `lead_field_id` (heredado de WebFormFieldBase) se expone acá tal cual sale
    # de la columna real -- id INTERNO, no public_uuid, a diferencia de `id` (BaseResponse.id, que
    # sí es el public_uuid del propio WebFormField). Se intentó tipear este campo como `str` y
    # "unresolverlo" al public_uuid del LeadField (mismo patrón que value en
    # FieldAutomationService), pero Pydantic v2 no coacciona int->str por defecto: la sola
    # declaración `lead_field_id: str` rompe la validación de CUALQUIER GET/PUT de WebForm, antes
    # de que el código de resolución llegue a correr (confirmado empíricamente). El front no debe
    # usar este campo para matchear contra LeadField -- debe usar `lead_field.id` (ya viene
    # resuelto en LeadFieldLiteResponse, ver frontend WebFormForm.tsx fieldToPost()).