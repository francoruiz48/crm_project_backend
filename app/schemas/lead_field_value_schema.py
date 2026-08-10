from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from app.schemas.lead_field_schema import LeadFieldDetailedResponse, LeadFieldLiteResponse, LeadFieldResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Union
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse

class LeadFieldValueBasicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    field: Optional[LeadFieldLiteResponse] = None
    value: Optional[Union[str, int, float, List[int]]] = None
    #active y nomenclator_items se agregan para que este schema "básico" tenga la misma forma que
    #el LeadFieldValue completo del frontend: RelatedLeadResponse lo usa para mandar los campos
    #title_order de un lead relacionado restringido, y el frontend arma el título reutilizando
    #getLeadTitleArray (leadUtils.ts) tal cual, sin tener que duplicar esa lógica acá ni allá.
    active: bool = True
    nomenclator_items: List[NomenclatorItemResponse] = []

class RelatedLeadResponse(BaseModel):
    # No hereda BaseResponse (standalone) -- alias a public_uuid declarado acá
    # directo, mismo criterio que base_schema.py.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: str = Field(validation_alias="public_uuid")
    #Uso interno nomás (LeadService._redact_inaccessible_related_leads la usa para decidir si
    #este lead relacionado queda "restricted"), nunca se manda al frontend (exclude=True).
    campaign_id: int = Field(exclude=True)
    #True si el usuario que pide el lead NO tiene acceso a la campaña de ESTE lead relacionado.
    #Ojo: esto y el recorte de field_values a solo title_order NO se resuelven acá (un
    #model_validator no vuelve a correr por una asignación posterior) — los completa
    #LeadService._redact_inaccessible_related_leads después de que el repositorio arma este
    #objeto, comparando campaign_id contra CampaignRepository.get_accessible_campaign_ids.
    restricted: bool = False
    field_values: List[LeadFieldValueBasicResponse] = []

class LeadFieldValueBase(BaseModel):
    field_id: int
    # Bug real encontrado 2026-07-30: value seguía tipado List[int] para campos SELECTOR/
    # CHECKBOX, pero NomenclatorItem.id que devuelve la API es public_uuid desde Fase 4 --
    # cualquier alta/edición real de un valor de este tipo rompía con 422. Se acepta también
    # uuid-string en la lista; LeadService._resolve_value_nomenclator_ids resuelve al id
    # interno antes de persistir (mismo criterio que _resolve_value_field_ids).
    #
    # Bug real encontrado 2026-07-30 (preexistente, no relacionado al cambio de arriba):
    # el Union tenía `float` ANTES que `int`. Pydantic v2 (modo smart), ante un bool de
    # Python (value=True/False, como manda cualquier campo BOOL), lo coacciona al primer
    # tipo compatible del Union -- con `float` primero, True/False quedaban en 1.0/0.0 en
    # vez de 1/0. _check_field_definition (lead_service.py) valida BOOL con
    # str(value).lower() in ("true","false","1","0") -- "1.0"/"0.0" no matchean, así que
    # CUALQUIER alta de Lead con un campo BOOL en True/False rompía con 400 "Se espera
    # Verdadero o Falso.". Con `int` antes que `float`, True/False coaccionan a 1/0 (int) y
    # el resto de los casos (float, str, list) no cambian.
    value: Optional[Union[List[Union[int, str]], int, float, str]] = None

class LeadFieldValueCreate(LeadFieldValueBase, BaseCreate):
    # Override: a diferencia de LeadFieldValueBase.field_id (int, lo que sigue esperando el
    # Response -- ver LeadFieldValueResponse más abajo, que reusa LeadFieldValueBase tal cual),
    # acá field_id acepta Union[int, str]. El frontend manda `field.id` (public_uuid, str -- Fase
    # 3 nunca migró específicamente este campo, a diferencia de campaign_id/team_id/
    # assigned_to_user_id/contact_state_id en LeadCreate/LeadUpdate, que sí lo son) y esto rompía
    # con 422 en cualquier alta/edición de Lead con campos dinámicos (backend/AGENTS.md
    # §18-decies). Se permite también int porque hay callers internos (lead_import_export_service.py,
    # web_form_public_controller.py) que arman este schema a mano con el id interno ya resuelto,
    # sin pasar por HTTP -- LeadService._resolve_value_field_ids detecta cuál es cuál (numérico
    # = ya resuelto, sigue de largo; si no, lo resuelve por public_uuid).
    field_id: Union[int, str]

class LeadFieldValueUpdate(BaseModel):
    # Nota: no se usa en ningún lado del código actual (LeadUpdate.values usa
    # LeadFieldValueCreate) -- se ordena igual que LeadFieldValueBase.value por
    # consistencia, mismo bug de Union float-antes-que-int.
    value: Optional[Union[List[int], int, float, str]] = None

class LeadFieldValueResponse(LeadFieldValueBase, BaseResponse):
    lead_id: int
    field: Optional[LeadFieldLiteResponse] = None
    nomenclator_items: List[NomenclatorItemResponse] = []
    related_leads: List[RelatedLeadResponse] = []

class LeadFieldValueDetailedResponse(LeadFieldValueBase, BaseDetailedResponse):
    lead_id: int
    field: Optional[LeadFieldDetailedResponse] = None
    nomenclator_items: List[NomenclatorItemResponse] = []
    related_leads: List[RelatedLeadResponse] = []
