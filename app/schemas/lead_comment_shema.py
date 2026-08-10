
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.lead_field_value_schema import LeadFieldValueCreate, LeadFieldValueDetailedResponse, LeadFieldValueResponse


class LeadCommentBase(BaseModel):
    content: str = Field(min_length=1, max_length=600)
    color : Optional[str] = Field(default=None)
    lead_id: int = Field(gt=0)

class LeadCommentCreate(LeadCommentBase, BaseCreate):
    # public_uuid de Lead (Fase 3). El Response sigue con el int interno viejo (FK embebida,
    # deliberadamente sin migrar -- ver backend/AGENTS.md §18).
    lead_id: str

class LeadCommentUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=600)
    color : Optional[str] = Field(default=None)

class LeadCommentResponse(LeadCommentBase, BaseResponse):
    pass

class LeadCommentDetailedResponse(LeadCommentBase, BaseDetailedResponse):
    pass


