
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import Optional


class CampaignBase(BaseModel):
    name: str
    description: Optional[str]
    workspace_id: int


class CampaignCreate(CampaignBase, BaseCreate):
    pass


class CampaignResponse(CampaignBase, BaseResponse):
    pass

class CampaignDetailedResponse(CampaignBase, BaseDetailResponse):
    pass


