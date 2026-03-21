from typing import Optional, Union
from app.core.security import get_current_user
from fastapi import Query, Depends
from app.controllers.base_controller import BaseController
from app.schemas.pagination_schema import PaginatedResponse
from app.services.campaign_service import CampaignService
from app.schemas.campaign_schema import CampaignDetailedResponse, CampaignResponse, CampaignCreate, CampaignUpdate
from app.core.constans import DEFAULT_PAGE_SIZE, PAGE_SIZE_LIMIT, READ_WRITE

class CampaignController(BaseController):
    router_prefix = "/campaigns"
    service = CampaignService
    schema_in = CampaignCreate
    schema_update = CampaignUpdate
    schema_out = CampaignResponse
    schema_out_detail = CampaignDetailedResponse
    enabled_methods = READ_WRITE

router = CampaignController.get_router()
