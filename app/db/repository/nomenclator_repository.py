from typing import Optional
from app.db.repository.base_repository import BaseRepository
from app.models.nomenclator import Nomenclator
from app.schemas.nomenclator_schema import NomenclatorResponse, NomenclatorDetailedResponse
from sqlalchemy import or_

class NomenclatorRepository(BaseRepository):
    model = Nomenclator
    schema_out = NomenclatorResponse
    schema_out_detail = NomenclatorDetailedResponse

    @classmethod
    def get_all(cls, session, page: int = 0, page_size: int = 0, only_active: bool = True, detailed: bool = False, 
                campaign_id: int = None, global_nomenclator: bool = None, search: str = None, search_fields: list = None, **kwargs):

        query = session.query(cls.model)

        query = cls._apply_tenant_filter(query)

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

        # 2. Lógica de Búsqueda Global (SEARCH)
        if search and search_fields:
            search_conditions = []
            for field in search_fields:
                if hasattr(cls.model, field):
                    column = getattr(cls.model, field)
                    # Preparamos la condición ILIKE
                    search_conditions.append(column.ilike(f"%{search}%"))
            if search_conditions:
                query = query.filter(or_(*search_conditions))

        # 3. Filtros Estándar (kwargs) - Ej: campaign_id=5
        for key, value in kwargs.items():
            if value is not None and hasattr(cls.model, key):
                query = query.filter(getattr(cls.model, key) == value)

        # 4. Ordenamiento (Default por ID descendente)
        query = query.order_by(cls.model.id.desc())

        total, query = cls._paginate(query, page, page_size)
        
        items = cls._execute_read_query(query, detailed)

        return total, items