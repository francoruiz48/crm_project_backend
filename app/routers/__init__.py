from fastapi import APIRouter
from app.controllers.lead_controller import router as leads_router
from app.controllers.lead_field_controller import router as lead_fields_router
from app.controllers.lead_field_type_controller import router as lead_field_types_router
from app.controllers.validation_rule_controller import router as validation_rules_router
from app.controllers.nomenclator_controller import router as nomenclator_router
from app.controllers.nomenclator_item_controller import router as nomenclator_item_router

router = APIRouter()

router.include_router(leads_router)
router.include_router(lead_fields_router)
router.include_router(lead_field_types_router)
router.include_router(validation_rules_router)
router.include_router(nomenclator_router)
router.include_router(nomenclator_item_router)