from fastapi import Depends

from app.controllers.base_controller import BaseController
from app.core.security import UserContext
from app.services.lead_state_service import LeadStateService
from app.schemas.lead_state_schema import LeadStateCreate, LeadStateListResponse, LeadStateResponse, LeadStateDetailedResponse, LeadStateUpdate
from app.core.constans import READ_WRITE
from typing import Union, List
from app.core.security import get_current_user_roles

class LeadStateController(BaseController):
    router_prefix = "/lead_states"
    service = LeadStateService
    schema_in = LeadStateCreate
    schema_update = LeadStateUpdate
    schema_out = LeadStateResponse
    schema_out_detail = LeadStateDetailedResponse
    enabled_methods = READ_WRITE

    @classmethod
    def get_router(cls):
        # Generamos el router con los métodos base (GET_ONE, POST, etc.)
        router = super().get_router()

        @router.get("/{id}/next-states", response_model=LeadStateListResponse)
        def get_allowed_next_states(
            id: int, 
            user_context: UserContext = Depends(get_current_user_roles)
        ):
            """
            Obtiene los estados de destino permitidos según el estado actual (ID).
            Útil para renderizar dropdowns de "Mover a..." en el detalle de un Lead o validaciones en vistas Kanban.
            """
            states_list = LeadStateService.get_allowed_next_states(current_state_id=id, user_context=user_context)
            
            # Devolvemos un Objeto {} con el Array [] adentro
            return {"data": states_list}

        return router

router = LeadStateController.get_router()