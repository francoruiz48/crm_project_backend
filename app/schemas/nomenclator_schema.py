
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse


class NomenclatorBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)

class NomenclatorCreate(NomenclatorBase, BaseCreate):
    parent_nomenclator_id: Optional[int] = Field(default=None, gt=0)

class NomenclatorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)

class NomenclatorResponse(NomenclatorBase, BaseResponse):
    organization_id: Optional[int] = Field(default=None, gt=0)
    parent_nomenclator: Optional["NomenclatorResponse"] = None

class NomenclatorDetailedResponse(NomenclatorBase, BaseDetailedResponse):
    sub_nomenclators: List["NomenclatorResponse"] = Field(default_factory=list)
    organization_id: Optional[int] = Field(default=None, gt=0)
    parent_nomenclator: Optional["NomenclatorResponse"] = None
