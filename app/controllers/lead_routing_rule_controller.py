from app.controllers.base_controller import BaseController
from app.services.lead_routing_rule_service import LeadRoutingRuleService
from app.schemas.lead_routing_rule_schema import LeadRoutingRuleCreate, LeadRoutingRuleDetailedResponse, LeadRoutingRuleResponse, LeadRoutingRuleUpdate
from app.core.constans import READ_WRITE

class LeadRoutingRuleController(BaseController):
    router_prefix = "/lead_routing_rules"
    service = LeadRoutingRuleService
    schema_in = LeadRoutingRuleCreate
    schema_update = LeadRoutingRuleUpdate
    schema_out = LeadRoutingRuleResponse
    schema_out_detail = LeadRoutingRuleDetailedResponse
    enabled_methods = READ_WRITE

router = LeadRoutingRuleController.get_router()