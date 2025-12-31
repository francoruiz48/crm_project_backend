from fastapi import APIRouter
from app.controllers.lead_controller import router as leads_router
from app.controllers.lead_field_controller import router as lead_fields_router
from app.controllers.lead_field_type_controller import router as lead_field_types_router
from app.controllers.validation_rule_controller import router as validation_rules_router
from app.controllers.nomenclator_controller import router as nomenclator_router
from app.controllers.nomenclator_item_controller import router as nomenclator_item_router
from app.controllers.campaign_controller import router as campaign_router
from app.controllers.security_controllers.user_controller import router as user_router
from app.controllers.security_controllers.role_controller import router as role_router
from app.controllers.security_controllers.permission_controller import router as permission_router


router = APIRouter()

router.include_router(leads_router)
router.include_router(lead_fields_router)
router.include_router(lead_field_types_router)
router.include_router(validation_rules_router)
router.include_router(nomenclator_router)
router.include_router(nomenclator_item_router)
router.include_router(campaign_router)
router.include_router(user_router)
router.include_router(role_router)
router.include_router(permission_router)
