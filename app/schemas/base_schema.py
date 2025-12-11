from datetime import datetime

class BaseResponse():
    id: int
    created_at: datetime
    updated_at: datetime
    active: bool

    model_config = {
        "from_attributes": True
    }

class BaseCreate():
    pass