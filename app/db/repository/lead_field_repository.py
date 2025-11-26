
from app.db.repository.base_repository import BaseRepository
from app.models.lead_field import LeadField
from app.schemas.lead_field_schema import LeadFieldResponse

class LeadFieldRepository(BaseRepository):
    model = LeadField
    schema_out = LeadFieldResponse
