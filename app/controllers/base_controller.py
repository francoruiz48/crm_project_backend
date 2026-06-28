from typing import Dict, Optional, Union
from fastapi import APIRouter, Body, HTTPException, Query, Depends, Request
from app.core.constans import DEFAULT_PAGE_SIZE
from app.core.security import PermissionChecker, get_current_user_roles
from app.schemas.pagination_schema import PaginatedResponse

class BaseController:
    router_prefix = ""
    service = None
    schema_in = None
    schema_update = None
    schema_out = None
    schema_out_detail = None
    enabled_methods = {"GET_ALL", "GET_ONE", "POST", "PUT", "DELETE", "ACTIVE", "PATCH"}
    allowed_filter_fields: Optional[set] = None  # None = sin restricción (backward compat)

    required_permissions: Dict[str, str] = {}

    @classmethod
    def _get_deps(cls, action: str):
        # ... (Tu lógica de dependencias se mantiene IGUAL) ...
        perm_codename = cls.required_permissions.get(action)
        if not perm_codename and cls.service and cls.service.repository:
            table_name = cls.service.repository.model.__tablename__
            action_map = {
                "create": "create", "read": "view", "update": "update",
                "delete": "delete", "disable": "update", "active": "update"
            }
            suffix = action_map.get(action)
            if suffix:
                perm_codename = f"{table_name}:{suffix}"

        if perm_codename:
            return [Depends(PermissionChecker(perm_codename))]
        return []

    @classmethod
    def get_router(cls):
        router = APIRouter(prefix=cls.router_prefix)

        # Definición de modelos para Swagger
        if cls.schema_out_detail:
            ResponseModelItem = Union[cls.schema_out_detail, cls.schema_out]
        else:
            ResponseModelItem = cls.schema_out

        ResponseModelPaginated = PaginatedResponse[ResponseModelItem]

        from pydantic import BaseModel
            
        # Esquema para recibir el arreglo
        class BulkIdsRequest(BaseModel):
            ids: list[int]

        # ---------------------------------------------------------
        # GET ALL
        # ---------------------------------------------------------
        if "GET_ALL" in cls.enabled_methods:
            @router.get("/", response_model=ResponseModelPaginated,
                        dependencies=cls._get_deps("read"))
            def get_all(
                request: Request,
                page: int = Query(1, ge=1),
                page_size: int = DEFAULT_PAGE_SIZE,
                only_active: bool = True, 
                detailed: bool = Query(False),
                search: str = Query(None, description="Búsqueda global"),
                search_fields: str = Query(None, description="Campos para búsqueda global, separados por comas"),
                order_by: str = Query(None, description="Campo por el cual ordenar"), 
                ascending: Optional[bool] = Query(None, description="Orden ascendente (true) o descendente (false)"),
                start_date: str = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
                end_date: str = Query(None, description="Fecha fin (YYYY-MM-DD)"),
                date_field: str = Query("created_at", description="Campo de fecha a filtrar (default: created_at)"),
                creator_name: str = Query(None, description="Filtrar por nombre del creador"),
                creator_email: str = Query(None, description="Filtrar por email del creador"),
                updater_name: str = Query(None, description="Filtrar por nombre del actualizador"),
                updater_email: str = Query(None, description="Filtrar por email del actualizador"),
                user_context = Depends(get_current_user_roles)
            ):
                # Definimos los parámetros reservados que no deben tratarse como filtros de columna
                reserved_params = {"page", "page_size", "only_active", "detailed", "search", "search_fields", "order_by", "ascending", "start_date", "end_date", "date_field", "creator_name", "creator_email", "updater_name", "updater_email"}

                # Convertimos el string "field1,field2" en una lista ["field1", "field2"]
                search_fields = [f.strip() for f in search_fields.split(",")] if search_fields else None

                # Atrapamos cualquier otro parámetro de la URL (ej: ?campaign_id=5&name=Test)
                dynamic_filters = {
                    key: value for key, value in request.query_params.items()
                    if key not in reserved_params
                    and (cls.allowed_filter_fields is None or key.replace("__ilike", "") in cls.allowed_filter_fields)
                }

                total, items_pydantic = cls.service.get_all(
                    user_context=user_context,
                    page=page,
                    page_size=page_size,
                    only_active=only_active, 
                    detailed=detailed,
                    search=search,
                    search_fields=search_fields, 
                    order_by=order_by,
                    ascending=ascending,
                    start_date=start_date,
                    end_date=end_date,
                    date_field=date_field,
                    creator_name=creator_name,
                    creator_email=creator_email,
                    updater_name=updater_name,
                    updater_email=updater_email,
                    **dynamic_filters
                )

                return PaginatedResponse.create(
                    items=items_pydantic,
                    total=total,
                    page=page,
                    page_size=page_size
                )

        
        if "POST" in cls.enabled_methods:
            @router.post("/", response_model=ResponseModelItem, 
                dependencies=cls._get_deps("create"))
            def create(obj_in: cls.schema_in = Body(...),
                       user_context = Depends(get_current_user_roles)):
                return cls.service.create(obj_in, user_context=user_context)

        if "PUT" in cls.enabled_methods:
            @router.put("/{obj_id}", response_model=ResponseModelItem, 
                dependencies=cls._get_deps("update"))
            def update(obj_id: int, obj_in: cls.schema_update = Body(...),
                       user_context = Depends(get_current_user_roles)):
                return cls.service.update(obj_id, obj_in, user_context=user_context)

        if "DELETE" in cls.enabled_methods:
            @router.delete("/{obj_id}", dependencies=cls._get_deps("delete"))
            def delete(obj_id: int, force: bool = Query(False, description="Hard delete forzado (solo estrategias C y E)"), user_context = Depends(get_current_user_roles)):
                return cls.service.delete(obj_id, user_context=user_context, force=force)
            
        if "DELETE" in cls.enabled_methods:                
            @router.post("/bulk-delete", dependencies=cls._get_deps("delete"))
            def bulk_delete(payload: BulkIdsRequest, user_context = Depends(get_current_user_roles)):
                if not payload.ids:
                    raise HTTPException(status_code=400, detail="Debe proporcionar al menos un ID para eliminar.")
                
                # Le pasamos la lista de IDs al servicio
                return cls.service.bulk_delete(payload.ids, user_context=user_context)

        if "ACTIVE" in cls.enabled_methods:
            @router.put("/active/{obj_id}", dependencies=cls._get_deps("active"))
            def set_active(obj_id: int, user_context = Depends(get_current_user_roles)):
                cls.service.set_active(obj_id, user_context=user_context)
                return {"actived": True}
            
        if "ACTIVE" in cls.enabled_methods:
            @router.post("/bulk-active", dependencies=cls._get_deps("active"))
            def bulk_set_active(payload: BulkIdsRequest, user_context = Depends(get_current_user_roles)):
                if not payload.ids:
                    raise HTTPException(status_code=400, detail="Debe proporcionar al menos un ID para activar.")
                return cls.service.bulk_set_active(payload.ids, user_context=user_context)

        if "DEACTIVATE" in cls.enabled_methods:
            @router.delete("/active/{obj_id}", dependencies=cls._get_deps("delete"))
            def deactivate(obj_id: int, user_context = Depends(get_current_user_roles)):
                """Desactiva (active=False) sin eliminar el registro."""
                return cls.service.deactivate(obj_id, user_context=user_context)
            
        if "GET_ONE" in cls.enabled_methods:
            @router.get("/{obj_id}", 
                response_model=ResponseModelItem, 
                dependencies=cls._get_deps("read"))
            def get_one(obj_id: int, detailed: bool = Query(False), user_context = Depends(get_current_user_roles)):
                # El repositorio ya devuelve un objeto Pydantic (Detail o Simple)
                obj = cls.service.get_by_id(obj_id, detailed=detailed, user_context=user_context)
                
                if not obj:
                    raise HTTPException(status_code=404, detail="No encontrado")
                return obj

        return router