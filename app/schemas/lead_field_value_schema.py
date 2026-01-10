from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse
from app.schemas.lead_field_schema import LeadFieldDetailedResponse, LeadFieldResponse
from pydantic import BaseModel
from typing import List, Optional, Union
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse


class LeadFieldValueBase(BaseModel):
    field_id: int
    value: Optional[Union[str, int, float, List[int]]] = None


class LeadFieldValueCreate(LeadFieldValueBase, BaseCreate):
    pass


class LeadFieldValueResponse(LeadFieldValueBase, BaseResponse):
    lead_id: int
    field: Optional[LeadFieldResponse] = None
    nomenclator_items: List[NomenclatorItemResponse] = []


class LeadFieldValueDetailedResponse(LeadFieldValueBase, BaseDetailResponse):
    lead_id: int
    field: Optional[LeadFieldDetailedResponse] = None
    nomenclator_items: List[NomenclatorItemResponse] = []
