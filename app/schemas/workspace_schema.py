
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from app.schemas.campaign_schema import CampaignResponse


class WorkspaceBase(BaseModel):
    name: str
    description: Optional[str]

class WorkspaceCreate(WorkspaceBase, BaseCreate):
    pass

class WorkspaceResponse(WorkspaceBase, BaseResponse):
    pass

class WorkspaceDetailedResponse(WorkspaceBase, BaseDetailResponse):
    campaigns: List[CampaignResponse] = []


    
