
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse


class NomenclatorBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    campaign_id: Optional[int] = Field(default=None, gt=0)
    parent_nomenclator_id: Optional[int] = Field(default=None, gt=0)

class NomenclatorCreate(NomenclatorBase, BaseCreate):
    pass

class NomenclatorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    campaign_id: Optional[int] = Field(default=None, gt=0)
    parent_nomenclator_id: Optional[int] = Field(default=None, gt=0)

class NomenclatorResponse(NomenclatorBase, BaseResponse):
    organization_id: Optional[int] = Field(default=None, gt=0)

class NomenclatorDetailResponse(NomenclatorBase, BaseDetailResponse):
    items: List[NomenclatorItemResponse] = Field(default_factory=list)
    sub_nomenclators: List["NomenclatorResponse"] = Field(default_factory=list)
    organization_id: Optional[int] = Field(default=None, gt=0)
