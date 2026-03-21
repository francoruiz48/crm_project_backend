from app.db.repository.base_repository import BaseRepository
from app.models.lead_routing_rule import LeadRoutingRule
from app.schemas.lead_routing_rule_schema import LeadRoutingRuleCreate, LeadRoutingRuleDetailedResponse, LeadRoutingRuleResponse

class LeadRoutingRuleRepository(BaseRepository):
    model = LeadRoutingRule
    schema_in = LeadRoutingRuleCreate
    schema_out = LeadRoutingRuleResponse
    schema_out_detail = LeadRoutingRuleDetailedResponse
