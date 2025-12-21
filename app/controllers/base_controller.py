from typing import Dict, List, Union
from fastapi import APIRouter, Body, HTTPException, Query, Depends
from app.core.security import PermissionChecker, get_current_user

class BaseController:
    router_prefix = ""
    service = None
    schema_in = None
    schema_out = None
    schema_out_detail = None
    enabled_methods = {"GET_ALL", "GET_ONE", "POST", "PUT", "DELETE"}

    required_permissions: Dict[str, str] = {}
    # -------------------------------------------------------------------------
    # Centraliza la lógica de conversión a Pydantic
    # -------------------------------------------------------------------------
    @classmethod
    def _serialize_list(cls, data: list, detailed: bool):
        """
        Convierte una lista de objetos ORM/Dict a la lista de Schemas correspondiente.
        """
        if not detailed:
            return [cls.schema_out.model_validate(item, from_attributes=True) for item in data]
        elif detailed and cls.schema_out_detail:
            return [cls.schema_out_detail.model_validate(item, from_attributes=True) for item in data]
        
        return data

    @classmethod
    def _get_deps(cls, action: str):
        """
        Genera dependencia de seguridad automática.
        1. Busca en required_permissions manual.
        2. Si no está, infiere del modelo: "{tablename}:{action}".
        """
        perm_codename = cls.required_permissions.get(action)
        
        # --- LÓGICA AUTOMÁTICA ---
        if not perm_codename and cls.service and cls.service.repository:
            # Obtenemos el nombre de la tabla (ej: 'lead', 'campaign')
            table_name = cls.service.repository.model.__tablename__
            
            # Mapeo de acciones del Controller a acciones del Permiso
            # Controller Action -> Permission Suffix
            action_map = {
                "create": "create",
                "read": "view",
                "update": "update",
                "delete": "delete",
                "disable": "update", # Desactivar suele ser un update
                "active": "update"
            }
            
            suffix = action_map.get(action)
            if suffix:
                perm_codename = f"{table_name}:{suffix}"
        # -------------------------

        if perm_codename:
            return [Depends(PermissionChecker(perm_codename))]
        
        return [] # Si no se pudo determinar, el endpoint queda público (o podrías forzar error)

    @classmethod
    def get_router(cls):
        router = APIRouter(prefix=cls.router_prefix)

        # Definición de modelos de respuesta para Swagger
        if cls.schema_out_detail:
            ResponseModel = Union[cls.schema_out_detail, cls.schema_out]
            ResponseModelList = List[Union[cls.schema_out_detail, cls.schema_out]]
        else:
            ResponseModel = cls.schema_out
            ResponseModelList = List[cls.schema_out]



        if "GET_ALL" in cls.enabled_methods:
            @router.get("/", response_model=ResponseModelList,
                        dependencies=cls._get_deps("read"))
            def get_all(
                only_active: bool = True, 
                detailed: bool = Query(False, description="Si es True, incluye relaciones.")
            ):
                data = cls.service.get_all(only_active, detailed=detailed)
                # REUTILIZACIÓN DEL HELPER
                return cls._serialize_list(data, detailed)

        # ... (Resto de métodos GET_ONE, POST, PUT, DELETE igual que antes) ...
        if "GET_ONE" in cls.enabled_methods:
            @router.get("/{obj_id}", response_model=ResponseModel, 
                dependencies=cls._get_deps("read"))
            def get_one(obj_id: int, detailed: bool = Query(False)):
                obj = cls.service.get_by_id(obj_id, detailed=detailed)
                if not obj:
                    raise HTTPException(status_code=404, detail="No encontrado")
                
                if not detailed:
                    return cls.schema_out.model_validate(obj, from_attributes=True)
                elif detailed and cls.schema_out_detail:
                    return cls.schema_out_detail.model_validate(obj, from_attributes=True)
                return obj

        if "POST" in cls.enabled_methods:
            @router.post("/", response_model=cls.schema_out, 
                dependencies=cls._get_deps("create"))
            def create(obj_in: cls.schema_in = Body(...),
                       current_user = Depends(get_current_user)
                       ):
                return cls.service.create(obj_in, created_by = current_user.id)

        if "PUT" in cls.enabled_methods:
            @router.put("/{obj_id}", response_model=cls.schema_out, 
                dependencies=cls._get_deps("update"))
            def update(obj_id: int, obj_in: cls.schema_in = Body(...)):
                return cls.service.update(obj_id, obj_in)

        if "DELETE" in cls.enabled_methods:
            @router.delete("/{obj_id}", 
                dependencies=cls._get_deps("delete"))
            def delete(obj_id: int):
                cls.service.delete(obj_id)
                return {"deleted": True}
            
        if "PUT" in cls.enabled_methods:
            @router.put("/disable/{obj_id}", 
                dependencies=cls._get_deps("disable"))
            def set_disable(obj_id: int):
                cls.service.set_disable(obj_id)
                return {"disabled": True}
            
        if "PUT" in cls.enabled_methods:
            @router.put("/active/{obj_id}", 
                dependencies=cls._get_deps("active"))
            def set_active(obj_id: int):
                cls.service.set_active(obj_id)
                return {"actived": True}

        return router