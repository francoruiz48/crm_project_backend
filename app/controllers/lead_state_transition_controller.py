from app.controllers.base_controller import BaseController
from app.core.security import get_current_user_roles
from app.services.lead_state_transition_service import LeadStateTransitionService
from app.schemas.lead_state_transition_schema import (
    LeadStateTransitionBulkCreate,
    LeadStateTransitionCreate, 
    LeadStateTransitionResponse, 
    LeadStateTransitionDetailedResponse,
    LeadStateTransitionUpdate
)
from typing import List, Union
from app.schemas.pagination_schema import PaginatedResponse
from fastapi import Body, Depends

class LeadStateTransitionController(BaseController):
    router_prefix = "/lead_state_transitions"
    service = LeadStateTransitionService
    schema_in = LeadStateTransitionCreate
    schema_update = LeadStateTransitionUpdate
    schema_out = LeadStateTransitionResponse
    schema_out_detail = LeadStateTransitionDetailedResponse

    # Limitamos los métodos: No permitimos PUT (es mejor borrar y recrear la regla) ni ACTIVE
    enabled_methods = {"GET ALL", "GET_ONE", "POST", "DELETE"}

    @classmethod
    def get_router(cls):
        # Generamos el router con los métodos base (GET_ONE, POST, etc.)
        router = super().get_router()

        if cls.schema_out_detail:
            ResponseModelItem = Union[cls.schema_out_detail, cls.schema_out]
        else:
            ResponseModelItem = cls.schema_out
            
        ResponseModelPaginated = PaginatedResponse[ResponseModelItem]        

        @router.post("/bulk", response_model=List[cls.schema_out_detail], dependencies=cls._get_deps("create"))
        def create_transitions_bulk(
            obj_in: LeadStateTransitionBulkCreate = Body(...),
            user_context = Depends(get_current_user_roles)
        ):
            return cls.service.create_bulk(obj_in, user_context=user_context)

        return router

router = LeadStateTransitionController.get_router()