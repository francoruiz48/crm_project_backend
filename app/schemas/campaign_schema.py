
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import Optional


class CampaignBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    workspace_id: int = Field(..., gt=0)
    lead_flow_id: Optional[int] = Field(default=None)

class CampaignCreate(CampaignBase, BaseCreate):
    pass

class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    lead_flow_id: Optional[int] = Field(default=None)

class CampaignResponse(CampaignBase, BaseResponse):
    organization_id : int

class CampaignDetailedResponse(CampaignBase, BaseDetailResponse):
    organization_id : int


