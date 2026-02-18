from typing import Dict, List, Union
from fastapi import APIRouter, Body, HTTPException, Query, Depends
from app.core.constans import DEFAULT_PAGE_SIZE, PAGE_SIZE_LIMIT
from app.core.security import PermissionChecker, get_current_user
from app.schemas.pagination_schema import PaginatedResponse

class BaseController:
    router_prefix = ""
    service = None
    schema_in = None
    schema_out = None
    schema_out_detail = None
    enabled_methods = {"GET_ALL", "GET_ONE", "POST", "PUT", "DELETE", "ACTIVE"}

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

        # ---------------------------------------------------------
        # GET ALL
        # ---------------------------------------------------------
        if "GET_ALL" in cls.enabled_methods:
            @router.get("/", response_model=ResponseModelPaginated,
                        dependencies=cls._get_deps("read"))
            def get_all(
                page: int = Query(1, ge=1),
                page_size: int = DEFAULT_PAGE_SIZE,
                only_active: bool = True, 
                detailed: bool = Query(False)
            ):
                total, items_pydantic = cls.service.get_all(
                    page=page,
                    page_size=page_size,
                    only_active=only_active, 
                    detailed=detailed
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
                       current_user = Depends(get_current_user)):
                return cls.service.create(obj_in, created_by=current_user.id)

        if "PUT" in cls.enabled_methods:
            @router.put("/{obj_id}", response_model=ResponseModelItem, 
                dependencies=cls._get_deps("update"))
            def update(obj_id: int, obj_in: cls.schema_in = Body(...)):
                return cls.service.update(obj_id, obj_in)

        if "DELETE" in cls.enabled_methods:
            @router.delete("/{obj_id}", dependencies=cls._get_deps("delete"))
            def delete(obj_id: int):
                return cls.service.delete(obj_id)
            
        #if "SOFT_DELETE" in cls.enabled_methods:
        #    @router.put("/disable/{obj_id}", dependencies=cls._get_deps("disable"))
        #    def set_disable(obj_id: int):
        #        cls.service.set_disable(obj_id)
        #        return {"disabled": True}
            
        if "ACTIVE" in cls.enabled_methods:
            @router.put("/active/{obj_id}", dependencies=cls._get_deps("active"))
            def set_active(obj_id: int):
                cls.service.set_active(obj_id)
                return {"actived": True}
            
        if "GET_ONE" in cls.enabled_methods:
            @router.get("/{obj_id}", 
                response_model=ResponseModelItem, 
                dependencies=cls._get_deps("read"))
            def get_one(obj_id: int, detailed: bool = Query(False)):
                # El repositorio ya devuelve un objeto Pydantic (Detail o Simple)
                obj = cls.service.get_by_id(obj_id, detailed=detailed)
                
                if not obj:
                    raise HTTPException(status_code=404, detail="No encontrado")
                return obj

        return router