
from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.lead_comment import LeadComment
from app.models.lead import Lead
from app.schemas.lead_comment_shema import LeadCommentCreate, LeadCommentDetailedResponse, LeadCommentResponse
from app.core.security import UserContext

class LeadCommentRepository(BaseRepository):
    model = LeadComment
    # Antes HARD_DELETE_ALWAYS: borrar un comentario lo eliminaba físicamente, sin dejar
    # ningún rastro visible (solo quedaba una entrada de SystemAuditLog, que es un log técnico
    # interno). Pedido del usuario: los comentarios son registro de interacciones con el cliente,
    # así que "eliminar" ahora es soft-delete (active=False) — desaparece del timeline (get_all
    # filtra por active=True por defecto) pero el dato queda en la base.
    delete_strategy = DeleteStrategy.SOFT_DELETE_ALWAYS
    schema_in = LeadCommentCreate
    schema_out = LeadCommentResponse
    schema_out_detail = LeadCommentDetailedResponse

    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext = None):
        if user_context is None or user_context.user is None:
            return query

        if user_context.is_superuser:
            return query

        if user_context.organization_id is None:
            return query

        return query.join(Lead, LeadComment.lead_id == Lead.id).filter(
            Lead.organization_id == user_context.organization_id
        )
