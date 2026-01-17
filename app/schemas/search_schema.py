from pydantic import BaseModel
from typing import List
from app.schemas.lead_schema import LeadResponse
from app.schemas.campaign_schema import CampaignResponse
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse
from app.schemas.nomenclator_schema import NomenclatorResponse
from app.schemas.workspace_schema import WorkspaceResponse

class GlobalSearchResponse(BaseModel):
    leads: List[LeadResponse] = []
    campaigns: List[CampaignResponse] = []
    workspaces: List[WorkspaceResponse] = []
    nomenclator_items: List[NomenclatorItemResponse] = []
    nomenclators: List[NomenclatorResponse] = []