from app.controllers.base_controller import BaseController
from app.services.campaign_service import CampaignService
from app.schemas.campaign_schema import CampaignResponse, CampaignCreate
from app.core.constans import READ_WRITE

class CampaignController(BaseController):
    router_prefix = "/campaigns"
    service = CampaignService
    schema_in = CampaignCreate
    schema_out = CampaignResponse
    enabled_methods = READ_WRITE

router = CampaignController.get_router()
