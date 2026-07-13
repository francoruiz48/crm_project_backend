
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional


class NomenclatorItemBase(BaseModel):
    value: str = Field(..., min_length=1, max_length=100)
    nomenclator_id: int = Field(gt=0)

class NomenclatorItemCreate(NomenclatorItemBase, BaseCreate):
    # Feature de nomencladores dependientes (ver docs/nomencladores.md): lista
    # de ítems padre — uno por cada catálogo padre válido que aplique (ej. una
    # ciudad puede tener como padre tanto su país como su región a la vez).
    # Reemplaza al viejo parent_item_id único.
    parent_item_ids: Optional[List[int]] = Field(default=None)

class NomenclatorItemUpdate(BaseModel):
    value: Optional[str] = Field(default=None, min_length=1, max_length=100)
    # Si viene, reemplaza la lista COMPLETA de ítems padre (no hace merge).
    parent_item_ids: Optional[List[int]] = Field(default=None)

class NomenclatorItemResponse(NomenclatorItemBase, BaseResponse):
    parent_items: List["NomenclatorItemResponse"] = Field(default_factory=list)
    organization_id: Optional[int] = Field(default=None, gt=0)

class NomenclatorItemDetailedResponse(NomenclatorItemBase, BaseDetailedResponse):
    parent_items: List["NomenclatorItemResponse"] = Field(default_factory=list)
    child_items: List["NomenclatorItemResponse"] = Field(default_factory=list)
    organization_id: Optional[int] = Field(default=None, gt=0)