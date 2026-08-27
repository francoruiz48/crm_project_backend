from typing import Optional
from app.core.constans import DeleteStrategy
from sqlalchemy import or_
from app.core.context import TENANT_ORG_ID
from app.core.security import UserContext
from app.db.repository.base_repository import BaseRepository
from app.models.lead_contact_state import LeadContactState
from app.schemas.lead_contact_state_schema import LeadContactStateResponse, LeadContactStateDetailedResponse

class LeadContactStateRepository(BaseRepository):
    model = LeadContactState
    delete_strategy = DeleteStrategy.SOFT_DELETE_ALWAYS
    schema_out = LeadContactStateResponse
    schema_out_detail = LeadContactStateDetailedResponse

    default_sort_column = "order"
    default_sort_asc = True