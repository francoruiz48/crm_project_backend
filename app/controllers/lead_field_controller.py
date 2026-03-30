from app.controllers.base_controller import BaseController
from app.services.lead_field_service import LeadFieldService
from app.schemas.lead_field_schema import LeadFieldCreate, LeadFieldDetailedResponse, LeadFieldOrderList, LeadFieldResponse, LeadFieldUpdate
from app.core.constans import READ_WRITE
from fastapi import Body, Depends
from app.core.security import get_current_user_roles

class LeadFieldController(BaseController):
    router_prefix = "/lead_fields"
    service = LeadFieldService
    schema_in = LeadFieldCreate
    schema_update = LeadFieldUpdate
    schema_out = LeadFieldResponse
    schema_out_detail = LeadFieldDetailedResponse
    enabled_methods = READ_WRITE

    @classmethod
    def get_router(cls):
        # Obtenemos el router base (GET, POST, etc.)
        router = super().get_router()

        # Añadimos el endpoint de reorder
        @router.patch("/reorder/bulk", dependencies=cls._get_deps("update"))
        def reorder_fields(
            obj_in: LeadFieldOrderList = Body(...),
            user_context = Depends(get_current_user_roles)
        ):
            return cls.service.reorder(obj_in, user_context=user_context)

        return router

router = LeadFieldController.get_router()