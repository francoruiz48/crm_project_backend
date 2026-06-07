
from typing import Optional
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, Field


class OrganizationBase(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    description: Optional[str] = Field(default=None, min_length=3, max_length=500)

class OrganizationCreate(OrganizationBase, BaseCreate):
    pass

class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=150)
    description: Optional[str] = Field(default=None, min_length=3, max_length=500)

class OrganizationResponse(OrganizationBase, BaseResponse):
    pass

class OrganizationDetailedResponse(OrganizationBase, BaseDetailedResponse):
    pass


