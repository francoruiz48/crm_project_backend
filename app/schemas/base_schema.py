from datetime import datetime
from typing import Optional

class BaseResponse():
    id: int

    model_config = {
        "from_attributes": True
    }

class BaseDetailResponse(BaseResponse):
    created_at: datetime
    updated_at: datetime
    active: bool
    created_by: Optional[int]
    updated_by: Optional[int]

class BaseCreate():
    pass