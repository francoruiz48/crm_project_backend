
from app.schemas.base_schema import BaseResponse, BaseCreate
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from app.schemas.campaign_schema import CampaignResponse


class WorkspaceBase(BaseModel):
    name: str
    description: Optional[str]

class WorkspaceCreate(WorkspaceBase, BaseCreate):
    pass

class WorkspaceResponse(WorkspaceBase, BaseResponse):
    campaigns: List[CampaignResponse] = []


    
