from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.field_automation import FieldAutomation
from app.models.campaign import Campaign
from app.schemas.field_automation_schema import FieldAutomationCreate, FieldAutomationDetailedResponse, FieldAutomationResponse
from app.core.security import UserContext

class FieldAutomationRepository(BaseRepository):
    model = FieldAutomation
    delete_strategy = DeleteStrategy.HARD_DELETE_WITH_TOGGLE
    schema_in = FieldAutomationCreate
    schema_out = FieldAutomationResponse
    schema_out_detail = FieldAutomationDetailedResponse

    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext = None):
        if user_context is None or user_context.user is None:
            return query

        if user_context.is_superuser:
            return query

        if user_context.organization_id is None:
            return query

        return query.join(Campaign, FieldAutomation.campaign_id == Campaign.id).filter(
            Campaign.organization_id == user_context.organization_id
        )
