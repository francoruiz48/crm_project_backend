from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.security_schemas.user_schema import UserResponse


class TeamMemberBase(BaseModel):
    role: str = Field(default="AGENT", pattern="^(MANAGER|AGENT)$")
    user_id: int = Field(..., gt=0)
    team_id: int = Field(..., gt=0)

class TeamMemberCreate(TeamMemberBase, BaseCreate):
    # public_uuid de User/Team (Fase 3). El Response sigue con el int interno viejo (FK
    # embebida, deliberadamente sin migrar -- ver backend/AGENTS.md §18).
    user_id: str
    team_id: str

class TeamMemberUpdate(BaseModel):
    role: Optional[str] = Field(default=None, pattern="^(MANAGER|AGENT)$")

class TeamMemberResponse(TeamMemberBase, BaseResponse):
    pass

class TeamMemberDetailedResponse(TeamMemberBase, BaseDetailedResponse):
    user: UserResponse

class BulkAssignRequest(BaseModel):
    # public_uuid de Lead/Team/User desde Fase 3 (LeadService.bulk_assign los resuelve a id
    # interno, ver backend/AGENTS.md §18).
    lead_ids: List[str] = Field(..., min_length=1, description="Lista de public_uuid de leads a reasignar")
    target_team_id: Optional[str] = None
    target_user_id: Optional[str] = None
    #target_team_id/target_user_id = None significa "no tocar este campo" (no "vaciarlo"), así que
    #para poder desasignar (dejar el lead sin equipo/usuario) hacen falta estos dos flags aparte.
    clear_team: bool = False
    clear_user: bool = False
