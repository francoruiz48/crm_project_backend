
from app.db.repository.base_repository import BaseRepository
from app.models.lead_field_subtype import LeadFieldSubtype
from app.schemas.lead_field_subtype_schema import LeadFieldSubtypeDetailedResponse, LeadFieldSubtypeResponse

class LeadFieldSubtypeRepository(BaseRepository):
    model = LeadFieldSubtype
    schema_out = LeadFieldSubtypeResponse
    schema_out_detail = LeadFieldSubtypeDetailedResponse
