from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.security_schemas.user_schema import UserResponse


class TeamMemberBase(BaseModel):
    role: str = Field(default="AGENT", pattern="^(MANAGER|AGENT)$")
    user_id: int = Field(..., gt=0)
    team_id: int = Field(..., gt=0)

class TeamMemberCreate(TeamMemberBase, BaseCreate):
    pass

class TeamMemberUpdate(BaseModel):
    role: Optional[str] = Field(default=None, pattern="^(MANAGER|AGENT)$")

class TeamMemberResponse(TeamMemberBase, BaseResponse):
    pass

class TeamMemberDetailedResponse(TeamMemberBase, BaseDetailedResponse):
    user: UserResponse

class BulkAssignRequest(BaseModel):
    lead_ids: List[int] = Field(..., min_length=1, description="Lista de IDs de leads a reasignar")
    target_team_id: Optional[int] = Field(None, gt=0)
    target_user_id: Optional[int] = Field(None, gt=0)
    #target_team_id/target_user_id = None significa "no tocar este campo" (no "vaciarlo"), así que
    #para poder desasignar (dejar el lead sin equipo/usuario) hacen falta estos dos flags aparte.
    clear_team: bool = False
    clear_user: bool = False
