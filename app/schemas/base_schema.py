from datetime import datetime
from typing import Optional

class BaseResponse():
    id: int
    created_at: datetime
    updated_at: datetime
    active: bool
    created_by: Optional[int]

    model_config = {
        "from_attributes": True
    }

class BaseCreate():
    pass