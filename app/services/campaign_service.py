from app.services.base_service import BaseService
from app.db.repository.campaign_repository import CampaignRepository

class CampaignService(BaseService):
    repository = CampaignRepository
