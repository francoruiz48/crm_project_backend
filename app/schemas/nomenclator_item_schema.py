
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional


class NomenclatorItemBase(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    value: str = Field(..., min_length=2, max_length=100)
    nomenclator_id: int = Field(gt=0)
    parent_item_id: Optional[int] = Field(default=None, gt=0)

class NomenclatorItemCreate(NomenclatorItemBase, BaseCreate):
    pass

class NomenclatorItemUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=50)
    value: Optional[str] = Field(default=None, min_length=2, max_length=100)
    parent_item_id: Optional[int] = Field(default=None, gt=0)

class NomenclatorItemResponse(NomenclatorItemBase, BaseResponse):
    organization_id: Optional[int] = Field(default=None, gt=0)

class NomenclatorItemDetailResponse(NomenclatorItemBase, BaseDetailResponse):
    parent_item: Optional["NomenclatorItemResponse"] = None
    organization_id: Optional[int] = Field(default=None, gt=0)