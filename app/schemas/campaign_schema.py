
from app.schemas.base_schema import BaseResponse, BaseCreate
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional


class CampaignBase(BaseModel):
    name: str
    description: Optional[str]


class CampaignCreate(CampaignBase, BaseCreate):
    pass


class CampaignResponse(CampaignBase, BaseResponse):
    pass

