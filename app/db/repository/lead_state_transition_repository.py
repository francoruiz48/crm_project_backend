
from app.db.repository.base_repository import BaseRepository
from app.models.lead_state_transition import LeadStateTransition
from app.schemas.lead_state_transition_schema import LeadStateTransitionCreate, LeadStateTransitionDetailedResponse, LeadStateTransitionResponse

class LeadStateTransitionRepository(BaseRepository):
    model = LeadStateTransition
    schema_in = LeadStateTransitionCreate
    schema_out = LeadStateTransitionResponse
    schema_out_detail = LeadStateTransitionDetailedResponse
