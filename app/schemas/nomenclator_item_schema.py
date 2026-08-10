
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional


# Versión liviana de NomenclatorResponse, declarada localmente para evitar el import
# circular (nomenclator_schema.py ya importa NomenclatorItemResponse de este módulo).
# Mismo patrón que LeadFieldLiteResponse en lead_field_schema.py.
class NomenclatorLiteResponse(BaseModel, BaseResponse):
    name: str


class NomenclatorItemBase(BaseModel):
    value: str = Field(..., min_length=1, max_length=100)
    nomenclator_id: int = Field(gt=0)

class NomenclatorItemCreate(NomenclatorItemBase, BaseCreate):
    # public_uuid de Nomenclator (Fase 3). El Response sigue con el int interno viejo (FK
    # embebida, deliberadamente sin migrar -- ver backend/AGENTS.md §18).
    nomenclator_id: str
    # Feature de nomencladores dependientes (ver docs/nomencladores.md): lista
    # de ítems padre — uno por cada catálogo padre válido que aplique (ej. una
    # ciudad puede tener como padre tanto su país como su región a la vez).
    # Reemplaza al viejo parent_item_id único. public_uuid de cada NomenclatorItem padre.
    parent_item_ids: Optional[List[str]] = Field(default=None)

class NomenclatorItemUpdate(BaseModel):
    value: Optional[str] = Field(default=None, min_length=1, max_length=100)
    # Si viene, reemplaza la lista COMPLETA de ítems padre (no hace merge).
    parent_item_ids: Optional[List[str]] = Field(default=None)

class NomenclatorItemResponse(NomenclatorItemBase, BaseResponse):
    parent_items: List["NomenclatorItemResponse"] = Field(default_factory=list)
    organization_id: Optional[int] = Field(default=None, gt=0)
    # Fase 4: objeto anidado con el uuid real (ver backend/AGENTS.md §18), nomenclator_id
    # de arriba sigue siendo la FK embebida sin migrar.
    nomenclator: Optional[NomenclatorLiteResponse] = None

class NomenclatorItemDetailedResponse(NomenclatorItemBase, BaseDetailedResponse):
    parent_items: List["NomenclatorItemResponse"] = Field(default_factory=list)
    child_items: List["NomenclatorItemResponse"] = Field(default_factory=list)
    organization_id: Optional[int] = Field(default=None, gt=0)
    nomenclator: Optional[NomenclatorLiteResponse] = None