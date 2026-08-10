
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Optional, Union

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

class LeadFlowDetailedResponse(LeadFlowBase, BaseDetailedResponse):
    organization_id: int = Field(gt=0)

class StateNodeSchema(BaseModel):
    # public_uuid (str) = estado ya existente en este flujo; int negativo (o None) = estado
    # nuevo, con un placeholder temporal que solo sirve para correlacionar transiciones dentro
    # de este mismo payload (ver LeadFlowOrchestratorService.save_graph, backend/AGENTS.md §18).
    # Antes esto era siempre un int (el id interno real para existentes); desde que el frontend
    # solo conoce public_uuid, un estado existente ya no puede identificarse con un int.
    id: Union[int, str, None] = Field(default=None, description="public_uuid si el estado ya existe; int negativo/None si es nuevo")
    name: str = Field(..., max_length=50)
    category: str = Field(..., pattern="^(OPEN|WON|LOST)$")
    is_initial: bool = False
    order: Optional[int] = None
    color: Optional[str] = None
    position_x: Optional[float] = 0.0
    position_y: Optional[float] = 0.0

class TransitionEdgeSchema(BaseModel):
    # Mismo esquema que StateNodeSchema.id: public_uuid si el estado en esa punta ya existe,
    # int negativo si es el placeholder de un estado nuevo del mismo payload.
    from_state_id: Union[int, str] = Field(description="public_uuid (existente) o int negativo (nuevo, mismo payload)")
    to_state_id: Union[int, str] = Field(description="public_uuid (existente) o int negativo (nuevo, mismo payload)")

class LeadFlowGraphPayload(BaseModel):
    # public_uuid del flujo (Fase 3). Si se envía, actualiza. Si es nulo, crea nuevo.
    id: Optional[str] = Field(default=None, description="public_uuid del flujo. Si se envía, actualiza. Si es nulo, crea nuevo.")
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    states: List[StateNodeSchema] = Field(default_factory=list)
    transitions: List[TransitionEdgeSchema] = Field(default_factory=list)