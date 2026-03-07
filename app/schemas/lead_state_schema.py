
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional

class LeadStateBase(BaseModel):
    lead_flow_id: int = Field(gt=0)
    name: str = Field(..., min_length=1, max_length=255)
    color: Optional[str] = Field(default=None, max_length=7)  # Ej: "#FF5733"
    category: str = Field(default="OPEN", pattern="^(OPEN|WON|LOST)$")
    is_initial: bool = Field(default=False)
    order: Optional[int] = Field(default=None, gt=0)

class LeadStateCreate(LeadStateBase, BaseCreate):
    pass

class LeadStateResponse(LeadStateBase, BaseResponse):
    organization_id: int

class LeadStateDetailedResponse(LeadStateBase, BaseDetailResponse):
    organization_id: int

