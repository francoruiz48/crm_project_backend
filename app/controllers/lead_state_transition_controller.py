from app.controllers.base_controller import BaseController
from app.core.security import get_current_user
from app.services.lead_state_transition_service import LeadStateTransitionService
from app.schemas.lead_state_transition_schema import (
    LeadStateTransitionBulkCreate,
    LeadStateTransitionCreate, 
    LeadStateTransitionResponse, 
    LeadStateTransitionDetailedResponse,
    LeadStateTransitionUpdate
)
from typing import List, Optional, Union
from app.schemas.pagination_schema import PaginatedResponse
from app.core.constans import DEFAULT_PAGE_SIZE
from fastapi import Body, Depends, Query

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
            current_user = Depends(get_current_user)
        ):
            return cls.service.create_bulk(obj_in, created_by=current_user.id)

        return router

router = LeadStateTransitionController.get_router()