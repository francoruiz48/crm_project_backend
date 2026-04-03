from typing import Optional
from app.core.security import UserContext
from app.db.repository.base_repository import BaseRepository
from app.models.nomenclator import Nomenclator
from app.schemas.nomenclator_schema import NomenclatorResponse, NomenclatorDetailedResponse
from sqlalchemy import or_

class NomenclatorRepository(BaseRepository):
    model = Nomenclator
    schema_out = NomenclatorResponse
    schema_out_detail = NomenclatorDetailedResponse

    @classmethod
    def get_all(cls, session, user_context: Optional[UserContext] = None, only_active: bool = True, detailed: bool = False, 
                campaign_id: int = None, global_nomenclator: bool = None, search: str = None, search_fields: list = None, **kwargs):

        query = session.query(cls.model)

        # 1. LÓGICA EXCLUSIVA DE NOMENCLADOR (Filtros de Campaña y Globales)
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

        return super().get_all(
            session=session,
            user_context=user_context,
            only_active=only_active,
            detailed=detailed,
            search=search,
            search_fields=search_fields,
            base_query=query,
            **kwargs
        )