from app.db.repository.base_repository import BaseRepository
from app.models.organization import Organization
from app.models.security_models import UserOrganization
from app.schemas.organization_schema import OrganizationResponse, OrganizationDetailedResponse
from app.core.security import UserContext


class OrganizationRepository(BaseRepository):
    model = Organization
    schema_out = OrganizationResponse
    schema_out_detail = OrganizationDetailedResponse

    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext = None):
        if user_context is None or user_context.user is None:
            return query

        if user_context.is_superuser:
            return query

        accessible_org_ids = session.query(UserOrganization.organization_id).filter(
            UserOrganization.user_id == user_context.user.id
        )
        return query.filter(cls.model.id.in_(accessible_org_ids))

