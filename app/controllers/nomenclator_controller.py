from app.controllers.base_controller import BaseController
from app.core.constans import DEFAULT_PAGE_SIZE, PAGE_SIZE_LIMIT
from app.schemas.pagination_schema import PaginatedResponse
from app.services.nomenclator_service import NomenclatorService
from app.schemas.nomenclator_schema import NomenclatorCreate, NomenclatorResponse, NomenclatorDetailedResponse, NomenclatorUpdate
from typing import List, Optional, Union
from fastapi import Depends, Query
from app.core.security import get_current_user

class NomenclatorController(BaseController):
    router_prefix = "/nomenclators"
    service = NomenclatorService
    schema_in = NomenclatorCreate
    schema_update = NomenclatorUpdate
    schema_out = NomenclatorResponse
    schema_out_detail = NomenclatorDetailedResponse
    
    # Quitamos "GET_ALL" de aquí para que BaseController NO genere el default
    enabled_methods = {"GET_ONE", "POST", "PUT", "DELETE", "ACTIVE", "PATCH"}

    @classmethod
    def get_router(cls):
        router = super().get_router()

        if cls.schema_out_detail:
            ResponseModelItem = Union[cls.schema_out_detail, cls.schema_out]
        else:
            ResponseModelItem = cls.schema_out
            
        ResponseModelPaginated = PaginatedResponse[ResponseModelItem]

        # 2. Definimos nuestro GET_ALL personalizado
        @router.get("/", response_model=ResponseModelPaginated)
        def get_all(
            page: int = Query(1, ge=1),
            page_size: int = DEFAULT_PAGE_SIZE,
            only_active: bool = True,
            detailed: bool = Query(False, description="Incluir relaciones"),
            search: str = Query(None, description="Búsqueda global"),
            search_fields: str = Query(None, description="Campos para búsqueda global, separados por comas"),
            current_user = Depends(get_current_user),
            campaign_id: Optional[int] = Query(None, description="Filtrar por ID de Campaña"),
            global_nomenclator: Optional[bool] = Query(None, description="Traer los nomencladores con campaña en null")
        ):
            search_fields = [f.strip() for f in search_fields.split(",")] if search_fields else None

            total, items_pydantic = cls.service.get_all(
                consulted_by=current_user.id,
                is_super_admin=getattr(current_user, 'is_superuser', False),
                search=search,
                search_fields=search_fields,
                page=page,
                page_size=page_size,
                only_active=only_active,
                detailed=detailed,
                campaign_id=campaign_id,
                global_nomenclator = global_nomenclator
            )
            
            return PaginatedResponse.create(
                items=items_pydantic,
                total=total,
                page=page,
                page_size=page_size
            )

        return router

router = NomenclatorController.get_router()
