
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional


class NomenclatorItemBase(BaseModel):
    code: str
    value: str
    nomenclator_id: int
    parent_item_id: Optional[int] = None


class NomenclatorItemCreate(NomenclatorItemBase, BaseCreate):
    pass


class NomenclatorItemResponse(NomenclatorItemBase, BaseResponse):
    pass

class NomenclatorItemDetailResponse(NomenclatorItemBase, BaseDetailResponse):
    parent_item: Optional["NomenclatorItemResponse"] = None