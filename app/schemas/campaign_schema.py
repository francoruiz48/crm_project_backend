
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from app.schemas.lead_flow_schema import LeadFlowResponse
from pydantic import BaseModel, computed_field, Field
from typing import Optional


# No se puede importar WorkspaceResponse de workspace_schema.py acá: ese módulo importa
# CampaignResponse de este archivo (para WorkspaceDetailedResponse.campaigns), así que sería un
# import circular. Se define una versión lite local, mismo criterio que NomenclatorLiteResponse
# (ver nomenclator_item_schema.py) y LeadFieldLiteResponse.
class WorkspaceLiteResponse(BaseModel, BaseResponse):
    name: str


class CampaignBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    workspace_id: int = Field(..., gt=0)
    lead_flow_id: Optional[int] = Field(default=None)
    is_public: bool = Field(default=True)

class CampaignCreate(CampaignBase, BaseCreate):
    # public_uuid de Workspace/LeadFlow (Fase 3). El Response sigue con el int interno viejo
    # (FK embebida, deliberadamente sin migrar por ahora -- ver backend/AGENTS.md §18).
    workspace_id: str
    lead_flow_id: Optional[str] = Field(default=None)
    target_audience: Optional[str] = Field(
        default="",
        description="Puede ser 'B2B' o 'B2C'."
    )

class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    lead_flow_id: Optional[str] = Field(default=None)  # public_uuid, ver CampaignCreate
    is_public: Optional[bool] = None

class CampaignResponse(CampaignBase, BaseResponse):
    organization_id : int
    # Fase 4 (patrón §18-bis): workspace_id/lead_flow_id de arriba siguen siendo el id interno
    # crudo (deuda deliberadamente no migrada, ver comentario en CampaignCreate) -- se agrega el
    # objeto anidado para exponer el uuid real, sin tocar el campo viejo (no rompe callers que ya
    # comparen ese int contra otro int). Las relaciones SQLAlchemy `workspace`/`lead_flow` ya
    # existían en el modelo (app/models/campaign.py), sin usar hasta ahora -- model_validate() las
    # resuelve solas (lazy load), mismo mecanismo que el resto de Fase 4.
    workspace: Optional[WorkspaceLiteResponse] = None
    lead_flow: Optional[LeadFlowResponse] = None

class CampaignDetailedResponse(CampaignBase, BaseDetailedResponse):
    organization_id : int
    workspace: Optional[WorkspaceLiteResponse] = None
    lead_flow: Optional[LeadFlowResponse] = None


