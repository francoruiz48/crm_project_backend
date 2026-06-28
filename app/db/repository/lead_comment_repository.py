
from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.lead_comment import LeadComment
from app.schemas.lead_comment_shema import LeadCommentCreate, LeadCommentDetailedResponse, LeadCommentResponse

class LeadCommentRepository(BaseRepository):
    model = LeadComment
    delete_strategy = DeleteStrategy.HARD_DELETE_ALWAYS
    schema_in = LeadCommentCreate
    schema_out = LeadCommentResponse
    schema_out_detail = LeadCommentDetailedResponse
