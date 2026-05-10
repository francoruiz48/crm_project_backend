from app.db.repository.base_repository import BaseRepository
from app.models.field_automation import FieldAutomation
from app.schemas.field_automation_schema import FieldAutomationCreate, FieldAutomationDetailedResponse, FieldAutomationResponse

class FieldAutomationRepository(BaseRepository):
    model = FieldAutomation
    schema_in = FieldAutomationCreate
    schema_out = FieldAutomationResponse
    schema_out_detail = FieldAutomationDetailedResponse
