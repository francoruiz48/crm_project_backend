
from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.lead_state import LeadState
from app.schemas.lead_state_schema import LeadStateCreate, LeadStateDetailedResponse, LeadStateResponse

class LeadStateRepository(BaseRepository):
    model = LeadState
    delete_strategy = DeleteStrategy.SOFT_DELETE_ALWAYS
    schema_in = LeadStateCreate
    schema_out = LeadStateResponse
    schema_out_detail = LeadStateDetailedResponse
