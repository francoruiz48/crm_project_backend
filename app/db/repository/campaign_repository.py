
from app.db.repository.base_repository import BaseRepository
from app.models.campaign import Campaign
from app.schemas.campaign_schema import CampaignCreate, CampaignResponse

class CampaignRepository(BaseRepository):
    model = Campaign
    schema_in = CampaignCreate
    schema_out = CampaignResponse
