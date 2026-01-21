from app.controllers.base_controller import BaseController
from app.services.lead_comment_service import LeadCommentService
from app.schemas.lead_comment_shema import LeadCommentCreate, LeadCommentDetailedResponse, LeadCommentResponse
from app.core.constans import READ_WRITE

class LeadCommentController(BaseController):
    router_prefix = "/lead_comments"
    service = LeadCommentService
    schema_in= LeadCommentCreate
    schema_out = LeadCommentResponse
    schema_out_detail = LeadCommentDetailedResponse
    enabled_methods = READ_WRITE

router = LeadCommentController.get_router()