from app.services.base_service import BaseService
from app.db.unit_of_work import UnitOfWork
from app.db.repository.lead_flow_repository import LeadFlowRepository

class LeadFlowService(BaseService):
    repository = LeadFlowRepository()

