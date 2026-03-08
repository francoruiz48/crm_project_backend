
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from app.schemas.campaign_schema import CampaignResponse


class WorkspaceBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)

class WorkspaceCreate(WorkspaceBase, BaseCreate):
    pass

class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)

class WorkspaceResponse(WorkspaceBase, BaseResponse):
    organization_id: int

class WorkspaceDetailedResponse(WorkspaceBase, BaseDetailResponse):
    organization_id: int
    campaigns: List[CampaignResponse] = []


    
