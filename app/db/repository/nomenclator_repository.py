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
    def get_all(cls, session, only_active: bool = True, detailed: bool = False, campaign_id: int = None, global_nomenclator: Optional[bool] = None):
        query = session.query(cls.model)

        # ESCENARIO A: Se solicitó una Campaña específica
        if campaign_id is not None:
            if global_nomenclator is True:
                # Trae la campaña específica + Globales
                # SQL: WHERE (campaign_id = 1 OR campaign_id IS NULL)
                query = query.filter(
                    or_(
                        cls.model.campaign_id == campaign_id,
                        cls.model.campaign_id.is_(None)
                    )
                )
            else:
                # Si es False o None: Trae SOLO esa campaña
                # "si es una campaña trae según la campaña"
                # SQL: WHERE campaign_id = 1
                query = query.filter(cls.model.campaign_id == campaign_id)

        # ESCENARIO B: No se especificó Campaña (campaign_id is None)
        else:
            if global_nomenclator is True:
                # "si global_nomenclator = True y campaign_id= None traiga solo los globales"
                # SQL: WHERE campaign_id IS NULL
                query = query.filter(cls.model.campaign_id.is_(None))
            
            elif global_nomenclator is False:
                # Solo campañas (cualquiera), excluye globales
                # SQL: WHERE campaign_id IS NOT NULL
                query = query.filter(cls.model.campaign_id.is_not(None))
            
            else:
                pass # No aplicamos ningún filtro, trae TODO.

        if only_active and hasattr(cls.model, "active"):
            query = query.filter(cls.model.active.is_(True))

        return cls._execute_read_query(query, detailed)