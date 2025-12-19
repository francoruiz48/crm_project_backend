from typing import List, Union
from fastapi import APIRouter, Body, HTTPException, Query

class BaseController:
    router_prefix = ""
    service = None
    schema_in = None
    schema_out = None
    schema_out_detail = None
    enabled_methods = {"GET_ALL", "GET_ONE", "POST", "PUT", "DELETE"}

    # -------------------------------------------------------------------------
    # NUEVO HELPER DRY: Centraliza la lógica de conversión a Pydantic
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
            @router.get("/", response_model=ResponseModelList)
            def get_all(
                only_active: bool = True, 
                detailed: bool = Query(False, description="Si es True, incluye relaciones.")
            ):
                data = cls.service.get_all(only_active, detailed=detailed)
                # REUTILIZACIÓN DEL HELPER
                return cls._serialize_list(data, detailed)

        # ... (Resto de métodos GET_ONE, POST, PUT, DELETE igual que antes) ...
        if "GET_ONE" in cls.enabled_methods:
            @router.get("/{obj_id}", response_model=ResponseModel)
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
            @router.post("/", response_model=cls.schema_out)
            def create(obj_in: cls.schema_in = Body(...)):
                return cls.service.create(obj_in)

        if "PUT" in cls.enabled_methods:
            @router.put("/{obj_id}", response_model=cls.schema_out)
            def update(obj_id: int, obj_in: cls.schema_in = Body(...)):
                return cls.service.update(obj_id, obj_in)

        if "DELETE" in cls.enabled_methods:
            @router.delete("/{obj_id}")
            def delete(obj_id: int):
                cls.service.delete(obj_id)
                return {"deleted": True}
            
        if "PUT" in cls.enabled_methods:
            @router.put("/disable/{obj_id}")
            def set_disable(obj_id: int):
                cls.service.set_disable(obj_id)
                return {"disabled": True}
            
        if "PUT" in cls.enabled_methods:
            @router.put("/active/{obj_id}")
            def set_active(obj_id: int):
                cls.service.set_active(obj_id)
                return {"actived": True}

        return router