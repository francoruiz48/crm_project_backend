from app.db.repository.base_repository import BaseRepository
from app.models.organization import Organization
from app.schemas.organization_schema import OrganizationResponse, OrganizationDetailedResponse


class OrganizationRepository(BaseRepository):
    model = Organization
    schema_out = OrganizationResponse
    schema_out_detail = OrganizationDetailedResponse

