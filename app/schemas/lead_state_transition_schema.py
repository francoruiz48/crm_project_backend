
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.lead_state_schema import LeadStateDetailedResponse

class LeadStateTransitionBase(BaseModel):
    lead_flow_id: int = Field(gt=0)
    from_state_id: int = Field(gt=0)
    to_state_id: int = Field(gt=0)

class LeadStateTransitionCreate(LeadStateTransitionBase, BaseCreate):
    # public_uuid de LeadFlow/LeadState (Fase 3). El Response sigue con los ints internos
    # viejos (FKs embebidas, deliberadamente sin migrar -- ver backend/AGENTS.md §18).
    lead_flow_id: str
    from_state_id: str
    to_state_id: str

class LeadStateTransitionUpdate(BaseModel):
    from_state_id: Optional[str] = None
    to_state_id: Optional[str] = None

class LeadStateTransitionResponse(LeadStateTransitionBase, BaseResponse):
    pass

class LeadStateTransitionDetailedResponse(LeadStateTransitionBase, BaseDetailedResponse):
    from_state : Optional[LeadStateDetailedResponse]
    to_state : LeadStateDetailedResponse

class TransitionPair(BaseModel):
    from_state_id: str
    to_state_id: str

class LeadStateTransitionBulkCreate(BaseModel):
    lead_flow_id: str
    transitions: List[TransitionPair] = Field(..., min_length=1)