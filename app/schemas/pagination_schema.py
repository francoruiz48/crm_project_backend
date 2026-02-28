from typing import Generic, TypeVar, List
from pydantic import BaseModel, Field
from math import ceil

# Definimos una variable genérica T (será UserResponse, LeadResponse, etc.)
T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    total: int = Field(..., description="Total de registros en la base de datos (sin paginar)")
    page: int = Field(..., description="Página actual")
    page_size: int = Field(..., description="Cantidad de registros por página")
    total_pages: int = Field(..., description="Total de páginas calculadas")
    items: List[T] = Field(..., description="Lista de registros de la página actual")

    # Helper para calcular total_pages automáticamente al crear la respuesta
    @classmethod
    def create(cls, items: List[T], total: int, page: int, page_size: int):
        total_pages = ceil(total / page_size) if page_size > 0 else 0
        
        actual_page = page
        if total_pages > 0 and page > total_pages:
            actual_page = total_pages
        return cls(
            total=total,
            page=actual_page,
            page_size=page_size,
            total_pages=total_pages,
            items=items
        )