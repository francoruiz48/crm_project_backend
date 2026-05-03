
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional


class NomenclatorItemBase(BaseModel):
    value: str = Field(..., min_length=1, max_length=100)
    nomenclator_id: int = Field(gt=0)
    
class NomenclatorItemCreate(NomenclatorItemBase, BaseCreate):
    parent_item_id: Optional[int] = Field(default=None, gt=0)

class NomenclatorItemUpdate(BaseModel):
    value: Optional[str] = Field(default=None, min_length=1, max_length=100)

class NomenclatorItemResponse(NomenclatorItemBase, BaseResponse):
    parent_item: Optional["NomenclatorItemResponse"] = None
    organization_id: Optional[int] = Field(default=None, gt=0)

class NomenclatorItemDetailedResponse(NomenclatorItemBase, BaseDetailResponse):
    parent_item: Optional["NomenclatorItemResponse"] = None
    organization_id: Optional[int] = Field(default=None, gt=0)