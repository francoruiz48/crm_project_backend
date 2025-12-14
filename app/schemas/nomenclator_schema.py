
from app.schemas.base_schema import BaseResponse, BaseCreate
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse


class NomenclatorBase(BaseModel):
    name: str
    campaign_id: Optional[int] = None
    parent_nomenclator_id: Optional[int] = None


class NomenclatorCreate(NomenclatorBase, BaseCreate):
    pass


class NomenclatorResponse(NomenclatorBase, BaseResponse):
    items: List[NomenclatorItemResponse] = Field(default_factory=list)

    sub_nomenclators: List["NomenclatorResponse"] = Field(default_factory=list)
