from app.services.base_service import BaseService
from app.db.repository.workspace_repository import WorkspaceRepository

class WorkspaceService(BaseService):
    repository = WorkspaceRepository
