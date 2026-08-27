from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.team_member_schema import TeamMemberResponse


class TeamBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    is_visibility_shared: bool = Field(default=True)


class TeamCreate(TeamBase, BaseCreate):
    pass

class TeamUpdate(TeamBase):
    pass

class TeamResponse(TeamBase, BaseResponse):
    organization_id: Optional[int] = Field(default=None, gt=0)

class TeamDetailedResponse(TeamBase, BaseDetailedResponse):
    organization_id: Optional[int] = Field(default=None, gt=0)
    members: List[TeamMemberResponse]


