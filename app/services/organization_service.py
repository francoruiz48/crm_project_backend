from app.services.base_service import BaseService
from app.db.repository.organization_repository import OrganizationRepository
from app.services.base_service import BaseService

class OrganizationService(BaseService):
    repository = OrganizationRepository

