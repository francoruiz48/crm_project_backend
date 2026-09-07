from pydantic import BaseModel

from app.schemas.base_schema import BaseDetailedResponse

class PermissionResponse(BaseModel, BaseResponse):
    name: str
    codename: str

    model_config = {
        "from_attributes": True
    }



