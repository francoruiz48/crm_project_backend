from app.services.base_service import BaseService
from app.db.repository.lead_comment_repository import LeadCommentRepository

class LeadCommentService(BaseService):
    repository = LeadCommentRepository
