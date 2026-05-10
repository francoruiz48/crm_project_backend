
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import Optional


class CampaignBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    workspace_id: int = Field(..., gt=0)
    lead_flow_id: Optional[int] = Field(default=None)
    is_public: bool = Field(default=True)

class CampaignCreate(CampaignBase, BaseCreate):
    target_audience: Optional[str] = Field(
        default="", 
        description="Puede ser 'B2B' o 'B2C'."
    )

class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    lead_flow_id: Optional[int] = Field(default=None)
    is_public: Optional[bool] = None

class CampaignResponse(CampaignBase, BaseResponse):
    organization_id : int

class CampaignDetailedResponse(CampaignBase, BaseDetailedResponse):
    organization_id : int


