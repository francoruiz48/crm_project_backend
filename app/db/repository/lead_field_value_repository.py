
from app.db.repository.base_repository import BaseRepository
from app.models.lead_field_value import LeadFieldValue
from app.schemas.lead_field_value_schema import LeadFieldValueResponse

class LeadFieldValueRepository(BaseRepository):
    model = LeadFieldValue
    schema_out = LeadFieldValueResponse