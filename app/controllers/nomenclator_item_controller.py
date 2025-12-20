from typing import List, Optional, Union
from fastapi import Query
from app.controllers.base_controller import BaseController
from app.services.nomenclator_item_service import NomenclatorItemService
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse, NomenclatorItemCreate, NomenclatorItemDetailResponse

class NomenclatorItemController(BaseController):
    router_prefix = "/nomenclator_items"
    service = NomenclatorItemService
    schema_in = NomenclatorItemCreate
    schema_out = NomenclatorItemResponse
    schema_out_detail = NomenclatorItemDetailResponse
    
    # Quitamos "GET_ALL" de aquí para que BaseController NO genere el default
    enabled_methods = {"GET_ONE", "POST", "PUT", "DELETE"} 

    @classmethod
    def get_router(cls):
        # Generamos el router con los métodos base (GET_ONE, POST, etc.)
        router = super().get_router()

        # Preparamos el modelo de respuesta (para Swagger)
        if cls.schema_out_detail:
            ResponseModelList = List[Union[cls.schema_out_detail, cls.schema_out]]
        else:
            ResponseModelList = List[cls.schema_out]

        # 2. Definimos nuestro GET_ALL personalizado
        @router.get("/", response_model=ResponseModelList)
        def get_all(
            only_active: bool = True,
            detailed: bool = Query(False, description="Incluir relaciones"),
            nomenclator_id: Optional[int] = Query(None, description="Filtrar por ID de Nomenclador"),
            parent_item_id: Optional[int] = Query(None, description="Filtrar por ID del padre del item")
        ):
            # Llamamos al servicio pasando el filtro
            data = cls.service.get_all(
                only_active=only_active, 
                detailed=detailed, 
                nomenclator_id=nomenclator_id,
                parent_item_id = parent_item_id
            )
            
            # 3. Usamos el helper DRY del padre para serializar
            return cls._serialize_list(data, detailed)

        return router

router = NomenclatorItemController.get_router()
