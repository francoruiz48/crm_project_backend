
from app.db.repository.base_repository import BaseRepository
from app.models.workspace import Workspace
from app.schemas.workspace_schema import WorkspaceCreate, WorkspaceResponse

class WorkspaceRepository(BaseRepository):
    model = Workspace
    schema_in = WorkspaceCreate
    schema_out = WorkspaceResponse
