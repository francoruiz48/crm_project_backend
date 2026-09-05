
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse, UserSimpleResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.schemas.lead_comment_shema import LeadCommentDetailedResponse
from app.schemas.lead_field_value_schema import LeadFieldValueCreate, LeadFieldValueDetailedResponse, LeadFieldValueResponse
from app.schemas.lead_state_schema import LeadStateDetailedResponse, LeadStateResponse
from app.schemas.tag_schema import TagResponse
from app.schemas.lead_contact_state_schema import LeadContactStateResponse, LeadContactStateDetailedResponse
from app.schemas.team_schema import TeamResponse
from app.schemas.campaign_schema import CampaignResponse


class LeadBase(BaseModel):
    # OJO: estos 4 campos son distintos en el payload de entrada (Create/Update) que en la
    # respuesta (Response, que hereda de LeadBase también): acá quedan tipados como el front
    # los sigue enviando HOY -- ver el override explícito de cada uno en LeadCreate/LeadUpdate
    # (público_uuid, ya que Fase 3 hizo que Campaign/Team/User/LeadContactState devuelvan su
    # id como public_uuid). El de acá (int) es el que sigue esperando la respuesta -- Fase 4
    # todavía no migró estos campos embebidos en las respuestas.
    campaign_id: int = Field(gt=0)
    assigned_to_user_id: Optional[int] = Field(default=None, gt=0)
    team_id: Optional[int] = Field(default=None, gt=0)
    contact_state_id: Optional[int] = Field(default=None, gt=0)
    picture_url: Optional[str] = None

class LeadCreate(LeadBase, BaseCreate):
    # Overrides: el front manda estos 3 como public_uuid (Campaign/Team/User), se resuelven a
    # id interno en LeadService.create/simulate_create antes de tocar la base de datos.
    campaign_id: str
    assigned_to_user_id: Optional[str] = None
    team_id: Optional[str] = None
    values: List[LeadFieldValueCreate]
    tag_ids: Optional[List[str]] = Field(default_factory=list)

class LeadUpdate(BaseModel):
    values: Optional[List[LeadFieldValueCreate]] = None
    # public_uuid de LeadContactState (ver comentario en LeadBase). Se resuelve a id interno en
    # LeadService.update (validación manual) y de nuevo, genéricamente, en BaseRepository.update.
    contact_state_id: Optional[str] = None
    # public_uuid de Tag. Se resuelve en LeadService._assign_tags vía Tag.public_uuid.
    tag_ids: Optional[List[str]] = Field(default_factory=list)

class LeadResponse(LeadBase, BaseResponse):
    field_values: List[LeadFieldValueResponse] = Field(
        default_factory=list
    )
    # Referencia legible para el usuario, ej. "L-0001" (pedido 2026-08-01, ver
    # backend/AGENTS.md §50). Optional porque algunos leads de test insertados directo por
    # ORM no tienen lead_number -- todo lead real creado por la API sí lo tiene.
    reference: Optional[str] = None
    organization_id : int
    current_state_id: int
    current_state: LeadStateResponse
    contact_state: Optional[LeadContactStateResponse] = None
    tags: List[TagResponse] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    team: Optional[TeamResponse] = None
    assigned_to_user: Optional[UserSimpleResponse] = None
    # created_by/updated_by (int interno) se sacaron de acá: son redundantes con
    # creator/updater (que ya traen el public_uuid) y quedaban expuestos por error --
    # LeadDetailedResponse ya no los tenía. Ver backend/AGENTS.md §53. Verificado
    # 2026-08-04: nada en el frontend ni en los tests lee lead.created_by/updated_by
    # desde la respuesta de la API (todo usa creator/updater).
    creator: Optional[UserSimpleResponse] = None
    updater: Optional[UserSimpleResponse] = None
    # Fase 4: objeto anidado con el uuid real (ver backend/AGENTS.md §18), mismo patrón que
    # team/assigned_to_user de arriba. campaign_id (LeadBase) sigue siendo la FK embebida.
    campaign: Optional[CampaignResponse] = None

class LeadLiteResponse(LeadBase, BaseResponse):
    organization_id : int
    current_state_id: int


class LeadIndicatorsResponse(BaseModel):
    """
    Indicadores fijos (todavia no editables por el usuario -- ver propuesta de modulo de
    Reportes/Indicadores del 2026-08-15) del lead individual. Se calculan en tiempo real al
    pedir el detalle (GET /leads/{id}?detailed=true), sin persistir nada nuevo.
    """
    days_since_created: int
    days_in_current_state: int
    # None si el lead nunca tuvo un CONTACT_STATE_CHANGED registrado en LeadActivityHistory
    # (todavia no fue contactado) -- no se puede calcular.
    days_to_first_contact: Optional[int] = None
    interactions_count: int
    days_since_last_activity: int
    # Cantidad de veces que el lead volvio a un estado del flujo en el que ya habia
    # estado antes (re-entradas a LeadStateHistory.to_state_id ya visto). Pedido por el
    # usuario 2026-08-15 junto con el rediseno en cards del detalle del lead.
    back_and_forth_count: int


class LeadDetailedResponse(LeadBase, BaseDetailedResponse):
    field_values: List[LeadFieldValueDetailedResponse] = Field(
        default_factory=list
    )
    # Ver comentario en LeadResponse.reference más arriba.
    reference: Optional[str] = None
    tags: List[TagResponse] = Field(default_factory=list)
    comments: List[LeadCommentDetailedResponse] = None
    organization_id : int
    current_state: LeadStateDetailedResponse
    current_state_id: int
    contact_state: Optional[LeadContactStateDetailedResponse] = None
    team: Optional[TeamResponse] = None
    assigned_to_user: Optional[UserSimpleResponse] = None
    campaign: Optional[CampaignResponse] = None
    indicators: Optional[LeadIndicatorsResponse] = None


