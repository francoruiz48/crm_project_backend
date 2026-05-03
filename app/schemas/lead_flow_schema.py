
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Optional

class LeadFlowBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)

class LeadFlowCreate(LeadFlowBase, BaseCreate):
    pass

class LeadFlowUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)

class LeadFlowResponse(LeadFlowBase, BaseResponse):
    organization_id: int = Field(gt=0)

class LeadFlowDetailedResponse(LeadFlowBase, BaseDetailResponse):
    organization_id: int = Field(gt=0)

class StateNodeSchema(BaseModel):
    id: int = Field(description="ID real o ID negativo temporal (ej: -1) para estados nuevos")
    name: str = Field(..., max_length=50)
    category: str = Field(...) # OPEN, WON, LOST
    is_initial: bool = False
    order: Optional[int] = None
    color: Optional[str] = None
    position_x: Optional[float] = 0.0
    position_y: Optional[float] = 0.0

class TransitionEdgeSchema(BaseModel):
    from_state_id: int = Field(description="Puede ser ID real o negativo")
    to_state_id: int = Field(description="Puede ser ID real o negativo")

class LeadFlowGraphPayload(BaseModel):
    id: Optional[int] = Field(default=None, description="Si se envía, actualiza. Si es nulo, crea nuevo.")
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    states: List[StateNodeSchema] = Field(default_factory=list)
    transitions: List[TransitionEdgeSchema] = Field(default_factory=list)