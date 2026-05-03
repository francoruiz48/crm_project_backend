from app.db.repository.base_repository import BaseRepository
from app.models.web_form_field import WebFormField
from app.schemas.web_form_field_schema import WebFormFieldResponse

class WebFormFieldRepository(BaseRepository):
    model = WebFormField
    schema_out = WebFormFieldResponse
    schema_out_detail = WebFormFieldResponse