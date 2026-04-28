from app.db.repository.base_repository import BaseRepository
from app.models.web_form import WebForm
from app.schemas.web_form_schema import WebFormResponse, WebFormDetailedResponse

class WebFormRepository(BaseRepository):
    model = WebForm
    schema_out = WebFormResponse
    schema_out_detail = WebFormDetailedResponse