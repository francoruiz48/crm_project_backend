
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from pydantic import BaseModel, computed_field, Field
from typing import List, Dict, Any, Optional
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse


class NomenclatorBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)

class NomenclatorCreate(NomenclatorBase, BaseCreate):
    # Feature de nomencladores dependientes (ver docs/nomencladores.md): lista
    # de catálogos declarados como "padre válido" de este — reemplaza al viejo
    # parent_nomenclator_id único, que solo admitía un padre por catálogo.
    # public_uuid de cada Nomenclator padre (Fase 3, ver backend/AGENTS.md §18);
    # el service los resuelve a id interno antes de usarlos.
    parent_nomenclator_ids: Optional[List[str]] = Field(default=None)

class NomenclatorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    # Si viene, reemplaza la lista COMPLETA de padres válidos (no hace merge
    # con los existentes) — mismo criterio que ya usa WebForm.update con sus campos.
    parent_nomenclator_ids: Optional[List[str]] = Field(default=None)

class NomenclatorResponse(NomenclatorBase, BaseResponse):
    organization_id: Optional[int] = Field(default=None, gt=0)
    parent_nomenclators: List["NomenclatorResponse"] = Field(default_factory=list)

class NomenclatorDetailedResponse(NomenclatorBase, BaseDetailedResponse):
    child_nomenclators: List["NomenclatorResponse"] = Field(default_factory=list)
    organization_id: Optional[int] = Field(default=None, gt=0)
    parent_nomenclators: List["NomenclatorResponse"] = Field(default_factory=list)
