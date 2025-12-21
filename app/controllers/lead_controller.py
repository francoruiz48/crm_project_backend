from typing import List, Union, Optional
from fastapi import Depends, Query
from app.controllers.base_controller import BaseController
from app.core.security import PermissionChecker, get_current_user
from app.services.lead_service import LeadService
from app.schemas.lead_schema import LeadCreate, LeadResponse

class LeadController(BaseController):
    router_prefix = "/leads"
    service = LeadService
    schema_in = LeadCreate
    schema_out = LeadResponse
    
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
        @router.get("/", response_model=ResponseModelList,
                dependencies=cls._get_deps("read"))
        def get_all(
            only_active: bool = True,
            detailed: bool = Query(False, description="Incluir relaciones"),
            campaign_id: Optional[int] = Query(None, description="Filtrar por ID de campaña")
        ):
            data = cls.service.get_all(
                only_active=only_active, 
                detailed=detailed, 
                campaign_id=campaign_id
            )
            
            # 3. Usamos el helper DRY del padre para serializar
            return cls._serialize_list(data, detailed)

        return router

router = LeadController.get_router()