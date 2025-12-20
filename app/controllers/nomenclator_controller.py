from app.controllers.base_controller import BaseController
from app.services.nomenclator_service import NomenclatorService
from app.schemas.nomenclator_schema import NomenclatorCreate, NomenclatorResponse, NomenclatorDetailResponse
from typing import List, Optional, Union
from fastapi import Query

class NomenclatorController(BaseController):
    router_prefix = "/nomenclators"
    service = NomenclatorService
    schema_in = NomenclatorCreate
    schema_out = NomenclatorResponse
    schema_out_detail = NomenclatorDetailResponse
    
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
            campaign_id: Optional[int] = Query(None, description="Filtrar por ID de Campaña"),
            global_nomenclator: Optional[bool] = Query(None, description="Traer los nomencladores con campaña en null")
        ):
            # Llamamos al servicio pasando el filtro
            data = cls.service.get_all(
                only_active=only_active, 
                detailed=detailed, 
                campaign_id=campaign_id,
                global_nomenclator = global_nomenclator
            )
            
            # 3. Usamos el helper DRY del padre para serializar
            return cls._serialize_list(data, detailed)

        return router

router = NomenclatorController.get_router()
