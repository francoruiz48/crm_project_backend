from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class UserSimpleResponse(BaseModel):
    id: int
    name: str
    email: str

    model_config = {"from_attributes": True}

class BaseResponse():
    id: int

    model_config = {
        "from_attributes": True
    }

class BaseDetailedResponse(BaseResponse):
    created_at: datetime
    updated_at: datetime
    active: bool
    created_by: Optional[int]
    updated_by: Optional[int]

    creator: Optional[UserSimpleResponse] = None
    updater: Optional[UserSimpleResponse] = None

class BaseCreate():
    pass