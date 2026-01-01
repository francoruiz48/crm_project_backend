from typing import Any, Optional, List, Union
from enum import Enum
from pydantic import BaseModel, Field

class FilterOperator(str, Enum):
    EQ = "eq"         # Igual (=)
    NEQ = "neq"       # No igual (!=)
    GT = "gt"         # Mayor que (>)
    LT = "lt"         # Menor que (<)
    GTE = "gte"       # Mayor o igual (>=)
    LTE = "lte"       # Menor o igual (<=)
    LIKE = "like"     # Contiene (texto)
    ILIKE = "ilike"   # Contiene (texto, ignora mayúsculas)
    IN = "in"         # Lista de opciones
    BETWEEN = "between"   # Entre dos valores (rangos)

class LeadFilter(BaseModel):
    field_id: int = Field(..., description="ID del campo dinámico (LeadField)")
    operator: FilterOperator = Field(..., description="Operador de comparación")
    value: Union[Any, List[Any]] = Field(..., description="Valor único o [min, max]")

class LeadSearchRequest(BaseModel):
    campaign_id: Optional[int] = None
    filters: List[LeadFilter] = []
    page: int = 1
    page_size: int = 50