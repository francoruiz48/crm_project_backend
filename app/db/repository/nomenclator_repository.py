from typing import Optional
from app.db.repository.base_repository import BaseRepository
from app.models.nomenclator import Nomenclator
from app.schemas.nomenclator_schema import NomenclatorResponse, NomenclatorDetailResponse
from sqlalchemy import or_

class NomenclatorRepository(BaseRepository):
    model = Nomenclator
    schema_out = NomenclatorResponse
    schema_out_detail = NomenclatorDetailResponse

    @classmethod
    def get_all(cls, session, page: int = 0, page_size: int = 0, only_active: bool = True, detailed: bool = False, 
                campaign_id: int = None, global_nomenclator: bool = None):

        query = session.query(cls.model)

        if campaign_id is not None:
            if global_nomenclator is True:
                query = query.filter(or_(cls.model.campaign_id == campaign_id, cls.model.campaign_id.is_(None)))
            else:
                query = query.filter(cls.model.campaign_id == campaign_id)
        else:
            if global_nomenclator is True:
                query = query.filter(cls.model.campaign_id.is_(None))
            elif global_nomenclator is False:
                query = query.filter(cls.model.campaign_id.is_not(None))

        if only_active and hasattr(cls.model, "active"):
            query = query.filter(cls.model.active.is_(True))

        total, query = cls._paginate(query, page, page_size)
        
        items = cls._execute_read_query(query, detailed)

        return total, items