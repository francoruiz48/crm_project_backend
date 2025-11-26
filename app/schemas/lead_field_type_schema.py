from pydantic import BaseModel

class LeadFieldTypeBase(BaseModel):
    code: str
    description: str


class LeadFieldTypeCreate(LeadFieldTypeBase):
    pass


class LeadFieldTypeResponse(LeadFieldTypeBase):
    id: int

    model_config = {
        "from_attributes": True
    }
