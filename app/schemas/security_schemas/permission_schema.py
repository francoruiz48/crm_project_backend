from pydantic import BaseModel

from app.schemas.base_schema import BaseDetailResponse

class PermissionResponse(BaseModel):
    name: str
    codename: str

    model_config = {
        "from_attributes": True
    }



