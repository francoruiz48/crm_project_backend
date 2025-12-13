from fastapi import APIRouter, Body, HTTPException

class BaseController:
    router_prefix = ""
    service = None
    schema_in = None
    schema_out = None
    enabled_methods = {"GET_ALL", "GET_ONE", "POST", "PUT", "DELETE"}

    @classmethod
    def get_router(cls):
        router = APIRouter(prefix=cls.router_prefix)

        if "GET_ALL" in cls.enabled_methods:
            @router.get("/", response_model=list[cls.schema_out])
            def get_all(only_active: bool = True):
                return cls.service.get_all(only_active)

        if "GET_ONE" in cls.enabled_methods:
            @router.get("/{obj_id}", response_model=cls.schema_out)
            def get_one(obj_id: int):
                obj = cls.service.get_by_id(obj_id)
                if not obj:
                    raise HTTPException(status_code=404, detail="No encontrado")
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
