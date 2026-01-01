from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from app.schemas.lead_field_schema import LeadFieldDetailedResponse, LeadFieldResponse
from pydantic import BaseModel
from typing import Optional
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse


class LeadFieldValueBase(BaseModel):
    field_id: int
    value: Optional[str] = None
    nomenclator_item_id: Optional[int] = None


class LeadFieldValueCreate(LeadFieldValueBase, BaseCreate):
    pass


class LeadFieldValueResponse(LeadFieldValueBase, BaseResponse):
    lead_id: int
    field: Optional[LeadFieldResponse] = None
    nomenclator_item: Optional[NomenclatorItemResponse] = None


class LeadFieldValueDetailedResponse(LeadFieldValueBase, BaseDetailResponse):
    lead_id: int
    field: Optional[LeadFieldDetailedResponse] = None
    nomenclator_item: Optional[NomenclatorItemResponse] = None
