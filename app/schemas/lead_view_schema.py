
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from app.schemas.team_schema import TeamResponse
from app.schemas.campaign_schema import CampaignResponse

class LeadViewBase(BaseModel):
    name: str = Field(..., example="Mis Leads Urgentes")
    visibility: str = Field(default="PRIVATE", pattern="^(PRIVATE|TEAM|PUBLIC)$")
    team_id: Optional[int] = None
    view_type: Optional[str] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
    ui_config: Dict[str, Any] = Field(default_factory=dict)
    sort_config: Dict[str, Any] = Field(default_factory=dict)

class LeadViewCreate(LeadViewBase, BaseCreate):
    # public_uuid de Campaign/Team (Fase 3, ver backend/AGENTS.md §18); el service/repository
    # los resuelve a id interno antes de usarlos.
    #
    # BUG encontrado y corregido en Fase 4: campaign_id vivía antes en LeadViewBase (compartido
    # con el Response) tipado `str` sin ningún alias/validator que tradujera el int interno real
    # de la columna a su uuid -- Pydantic v2 NO convierte int a str automáticamente (a
    # diferencia de v1), así que CUALQUIER lectura de una vista (list/get) tiraba
    # ValidationError 500. Se separa acá: Create/Update piden el uuid (str), el Response
    # vuelve a exponer el int interno viejo (FK embebida, igual que el resto de la deuda de
    # §18) + un objeto anidado `campaign` con el uuid real (mismo patrón que RoutingPolicy/
    # TeamAccess/NomenclatorItem).
    campaign_id: str
    team_id: Optional[str] = None

class LeadViewUpdate(BaseModel):
    name: Optional[str] = None
    visibility: Optional[str] = Field(default=None, pattern="^(PRIVATE|TEAM|PUBLIC)$")
    team_id: Optional[str] = None
    view_type: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    ui_config: Optional[Dict[str, Any]] = None
    sort_config: Optional[Dict[str, Any]] = None

class LeadViewResponse(LeadViewBase, BaseResponse):
    # FK embebida: sigue siendo el id interno viejo (sin migrar, ver backend/AGENTS.md §18).
    campaign_id: int
    organization_id: int
    # Fase 4: objetos anidados con el uuid real.
    campaign: Optional[CampaignResponse] = None
    team: Optional[TeamResponse] = None

class LeadViewDetailedResponse(LeadViewBase, BaseDetailedResponse):
    campaign_id: int
    organization_id: int
    campaign: Optional[CampaignResponse] = None
    team: Optional[TeamResponse] = None

