from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.web_form import WebForm
from app.schemas.web_form_schema import WebFormResponse, WebFormDetailedResponse

class WebFormRepository(BaseRepository):
    model = WebForm
    delete_strategy = DeleteStrategy.SOFT_DELETE_HARD_OPT
    schema_out = WebFormResponse
    schema_out_detail = WebFormDetailedResponse