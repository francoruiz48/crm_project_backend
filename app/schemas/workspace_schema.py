
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from app.schemas.campaign_schema import CampaignResponse


class WorkspaceBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(..., max_length=500)
    organization_id: int = Field(gt=0)

class WorkspaceCreate(WorkspaceBase, BaseCreate):
    pass

class WorkspaceResponse(WorkspaceBase, BaseResponse):
    pass

class WorkspaceDetailedResponse(WorkspaceBase, BaseDetailResponse):
    campaigns: List[CampaignResponse] = []


    
