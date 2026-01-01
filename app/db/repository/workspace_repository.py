
from app.db.repository.base_repository import BaseRepository
from app.models.workspace import Workspace
from app.schemas.workspace_schema import WorkspaceCreate, WorkspaceDetailedResponse, WorkspaceResponse

class WorkspaceRepository(BaseRepository):
    model = Workspace
    schema_in = WorkspaceCreate
    schema_out = WorkspaceResponse
    schema_out_detail = WorkspaceDetailedResponse
