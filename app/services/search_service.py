from sqlalchemy.orm import Session
from app.db.repository.lead_repository import LeadRepository
from app.db.repository.campaign_repository import CampaignRepository
from app.db.repository.nomenclator_item_repository import NomenclatorItemRepository
from app.db.repository.nomenclator_repository import NomenclatorRepository
from app.db.repository.workspace_repository import WorkspaceRepository

class SearchService:
    
    @classmethod
    def global_search(cls, session: Session, query: str):
        results = {}

        # Usamos "_" para ignorar el total y nos quedamos con la lista
        _, campaigns_list = CampaignRepository.get_all(
            session, 
            search=query, 
            search_fields=["name", "description"], 
            page=1, 
            page_size=5
        )
        results["campaigns"] = campaigns_list

        _, workspaces_list = WorkspaceRepository.get_all(
            session, 
            search=query, 
            search_fields=["name"], 
            page=1, 
            page_size=5
        )
        results["workspaces"] = workspaces_list

        _, items_list = NomenclatorItemRepository.get_all(
            session, 
            search=query, 
            search_fields=["code", "value"], 
            page=1, 
            page_size=5
        )
        results["nomenclator_items"] = items_list

        _, items_list = NomenclatorRepository.get_all(
            session, 
            search=query, 
            search_fields=["name"], 
            page=1, 
            page_size=5
        )
        results["nomenclators"] = items_list

        results["leads"] = LeadRepository.get_all(
            session, 
            search=query, 
            page=1, 
            page_size=5 
        )[1]

        return results