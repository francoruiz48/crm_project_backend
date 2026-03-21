from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field
from typing import Optional

class LeadRoutingRuleBase(BaseModel):
    campaign_id : Optional[int] = Field(default=None, gt=0)
    condition_type: str = Field(default="CUSTOM_FIELD", pattern="^(NOMENCLATOR|CUSTOM_FIELD)$")
    condition_target_id: int = Field(gt=0)
    condition_value: str
    target_team_id: int = Field(gt=0)
    order: Optional[int] = Field(default=None, gt=0)

class LeadRoutingRuleCreate(LeadRoutingRuleBase, BaseCreate):
    pass

class LeadRoutingRuleUpdate(BaseModel):
    condition_value: Optional[str]
    order: Optional[int] = Field(default=None, gt=0)

class LeadRoutingRuleResponse(LeadRoutingRuleBase, BaseResponse):
    organization_id: int

class LeadRoutingRuleDetailedResponse(LeadRoutingRuleBase, BaseDetailResponse):
    organization_id: int
    