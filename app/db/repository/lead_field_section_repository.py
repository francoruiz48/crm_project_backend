
from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.lead_field_section import LeadFieldSection
from app.schemas.lead_field_section_schema import LeadFieldSectionCreate, LeadFieldSectionDetailedResponse, LeadFieldSectionResponse

class LeadFieldSectionRepository(BaseRepository):
    model = LeadFieldSection
    delete_strategy = DeleteStrategy.SOFT_DELETE_ALWAYS
    schema_in = LeadFieldSectionCreate
    schema_out = LeadFieldSectionResponse
    schema_out_detail = LeadFieldSectionDetailedResponse
