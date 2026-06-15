
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional

class LeadStateBase(BaseModel):
    lead_flow_id: int = Field(gt=0)
    name: str = Field(..., min_length=1, max_length=255)
    color: Optional[str] = Field(default=None, max_length=7)  # Ej: "#FF5733"
    category: str = Field(default="OPEN", pattern="^(OPEN|WON|LOST)$")
    is_initial: bool = Field(default=False)
    order: Optional[int] = Field(default=None, gt=0)
    position_x: Optional[float] = Field(default=0.0, description="Coordenada X en la interfaz gráfica")
    position_y: Optional[float] = Field(default=0.0, description="Coordenada Y en la interfaz gráfica")

class LeadStateCreate(LeadStateBase, BaseCreate):
    pass

class LeadStateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    color: Optional[str] = Field(default=None, max_length=7)  # Ej: "#FF5733"
    category: Optional[str] = Field(default=None, pattern="^(OPEN|WON|LOST)$")
    is_initial: Optional[bool] = None
    order: Optional[int] = Field(default=None, gt=0)
    position_x: Optional[float] = Field(default=None, description="Coordenada X en la interfaz gráfica")
    position_y: Optional[float] = Field(default=None, description="Coordenada Y en la interfaz gráfica")

class LeadStateResponse(LeadStateBase, BaseResponse):
    organization_id: int

class LeadStateDetailedResponse(LeadStateBase, BaseDetailedResponse):
    organization_id: int

class LeadStateListResponse(BaseModel):
    data: List[LeadStateResponse]