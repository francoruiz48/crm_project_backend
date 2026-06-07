from typing import Optional
from pydantic import BaseModel, Field
from app.schemas.base_schema import BaseCreate, BaseResponse, BaseDetailedResponse

class LeadContactStateBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    color: Optional[str] = Field(default=None, max_length=7)
    is_initial: Optional[bool] = Field(default=False)
    order: Optional[int] = None

class LeadContactStateCreate(LeadContactStateBase, BaseCreate):
    pass

class LeadContactStateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    color: Optional[str] = Field(default=None, max_length=7)
    is_initial: Optional[bool] = Field(default=None)
    order: Optional[int] = None

class LeadContactStateResponse(LeadContactStateBase, BaseResponse):
    organization_id: int

class LeadContactStateDetailedResponse(LeadContactStateResponse, BaseDetailedResponse):
    pass