
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class LeadViewBase(BaseModel):
    name: str = Field(..., example="Mis Leads Urgentes")
    campaign_id: int
    visibility: str = Field(default="PRIVATE", pattern="^(PRIVATE|TEAM|PUBLIC)$")
    team_id: Optional[int] = None
    view_type: Optional[str] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
    ui_config: Dict[str, Any] = Field(default_factory=dict)
    sort_config: Dict[str, Any] = Field(default_factory=dict)

class LeadViewCreate(LeadViewBase, BaseCreate):
    pass

class LeadViewUpdate(BaseModel):
    name: Optional[str] = None
    visibility: Optional[str] = Field(default=None, pattern="^(PRIVATE|TEAM|PUBLIC)$")
    team_id: Optional[int] = None
    view_type: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    ui_config: Optional[Dict[str, Any]] = None
    sort_config: Optional[Dict[str, Any]] = None

class LeadViewResponse(LeadViewBase, BaseResponse):
    organization_id: int

class LeadViewDetailedResponse(LeadViewBase, BaseDetailedResponse):
    organization_id: int

