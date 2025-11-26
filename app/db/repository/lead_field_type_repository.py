
from app.db.repository.base_repository import BaseRepository
from app.models.lead_field_type import LeadFieldType
from app.schemas.lead_field_type_schema import LeadFieldTypeResponse

class LeadFieldTypeRepository(BaseRepository):
    model = LeadFieldType
    schema_out = LeadFieldTypeResponse
