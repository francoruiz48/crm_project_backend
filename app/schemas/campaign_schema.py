
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import Optional


class CampaignBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    workspace_id: int = Field(default=None, gt=0)
    lead_flow_id: int = Field(gt=0)

class CampaignCreate(CampaignBase, BaseCreate):
    pass


class CampaignResponse(CampaignBase, BaseResponse):
    organization_id : int

class CampaignDetailedResponse(CampaignBase, BaseDetailResponse):
    organization_id : int


