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
    model_config = ConfigDict(from_attributes=True)
    id: int
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
    value: Optional[Union[List[int], float, int, str]] = None

class LeadFieldValueCreate(LeadFieldValueBase, BaseCreate):
    pass

class LeadFieldValueUpdate(BaseModel):
    value: Optional[Union[List[int], float, int, str]] = None

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
