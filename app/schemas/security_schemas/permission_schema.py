from pydantic import BaseModel

from app.schemas.base_schema import BaseDetailedResponse
from app.schemas.base_schema import BaseResponse

class PermissionResponse(BaseModel, BaseResponse):
    name: str
    codename: str

    model_config = {
        "from_attributes": True
    }



