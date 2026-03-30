
from app.db.repository.base_repository import BaseRepository
from app.models.lead_flow import LeadFlow
from app.schemas.lead_flow_schema import LeadFlowCreate, LeadFlowDetailedResponse, LeadFlowResponse

class LeadFlowRepository(BaseRepository):
    model = LeadFlow
    schema_in = LeadFlowCreate
    schema_out = LeadFlowResponse
    schema_out_detail = LeadFlowDetailedResponse
