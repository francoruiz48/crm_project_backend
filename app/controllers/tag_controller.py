from app.controllers.base_controller import BaseController
from app.services.tag_service import TagService
from app.schemas.tag_schema import TagCreate, TagResponse, TagDetailedResponse, TagUpdate
from app.core.constans import READ_WRITE

class TagController(BaseController):
    router_prefix = "/tags"
    service = TagService
    schema_in = TagCreate
    schema_update = TagUpdate
    schema_out = TagResponse
    schema_out_detail = TagDetailedResponse
    enabled_methods = READ_WRITE

    allowed_filter_fields = {"name"}


router = TagController.get_router()