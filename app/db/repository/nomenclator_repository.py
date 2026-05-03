from typing import Optional
from app.core.context import TENANT_ORG_ID
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
                search: str = None, search_fields: list = None, **kwargs):

        query = session.query(cls.model)

        if user_context and user_context.organization_id is not None:
            org_id = user_context.organization_id
        else:
            org_id = TENANT_ORG_ID.get()

        if org_id is not None:
            query = query.filter(or_(cls.model.organization_id == org_id, cls.model.organization_id.is_(None)))
        else:
            query = query.filter(cls.model.organization_id.is_(None))

        # Delegamos al padre (la paginación, ordenamiento y busqueda de texto)
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