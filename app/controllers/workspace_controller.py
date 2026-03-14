from app.controllers.base_controller import BaseController
from app.services.workspace_service import WorkspaceService
from app.schemas.workspace_schema import WorkspaceDetailedResponse, WorkspaceResponse, WorkspaceCreate, WorkspaceUpdate
from app.core.constans import READ_WRITE

class WorkspaceController(BaseController):
    router_prefix = "/workspaces"
    service = WorkspaceService
    schema_in = WorkspaceCreate
    schema_update = WorkspaceUpdate
    schema_out = WorkspaceResponse
    schema_out_detail = WorkspaceDetailedResponse
    enabled_methods = READ_WRITE

router = WorkspaceController.get_router()
