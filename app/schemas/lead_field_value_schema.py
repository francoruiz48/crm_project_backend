from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse
from app.schemas.lead_field_schema import LeadFieldDetailedResponse, LeadFieldLiteResponse, LeadFieldResponse
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Union
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse

class LeadFieldValueBasicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    field: Optional[LeadFieldLiteResponse] = None
    value: Optional[Union[str, int, float, List[int]]] = None

class RelatedLeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    field_values: List[LeadFieldValueBasicResponse] = []

class LeadFieldValueBase(BaseModel):
    field_id: int
    value: Optional[Union[List[int], float, int, str]] = None

class LeadFieldValueCreate(LeadFieldValueBase, BaseCreate):
    pass

class LeadFieldValueUpdate(BaseModel):
    value: Optional[Union[List[int], float, int, str]] = None

class LeadFieldValueResponse(LeadFieldValueBase, BaseResponse):
    lead_id: int
    field: Optional[LeadFieldLiteResponse] = None
    nomenclator_items: List[NomenclatorItemResponse] = []
    related_leads: List[RelatedLeadResponse] = []

class LeadFieldValueDetailedResponse(LeadFieldValueBase, BaseDetailedResponse):
    lead_id: int
    field: Optional[LeadFieldDetailedResponse] = None
    nomenclator_items: List[NomenclatorItemResponse] = []
    related_leads: List[RelatedLeadResponse] = []
