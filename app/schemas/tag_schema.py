from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.base_schema import BaseCreate, BaseResponse, BaseDetailedResponse

class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    color: str = Field(default="#3B82F6")

class TagCreate(TagBase, BaseCreate):
    pass

class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    color: Optional[str] = Field(None)

class TagResponse(TagBase, BaseResponse):
    organization_id: int

class TagDetailedResponse(TagResponse, BaseDetailedResponse):
    pass