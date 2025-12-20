from app.db.repository.base_repository import BaseRepository
from app.models.nomenclator_item import NomenclatorItem
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse, NomenclatorItemDetailResponse


class NomenclatorItemRepository(BaseRepository):
    model = NomenclatorItem
    schema_out = NomenclatorItemResponse
    schema_out_detail = NomenclatorItemDetailResponse


    @classmethod
    def get_all(cls, session, only_active: bool = True, detailed: bool = False, nomenclator_id: int = None, parent_item_id: int = None):
        query = session.query(cls.model)

        if nomenclator_id is not None:
            query = query.filter(cls.model.nomenclator_id == nomenclator_id)

        if parent_item_id is not None:
            query = query.filter(cls.model.parent_item_id == parent_item_id)

        if only_active and hasattr(cls.model, "active"):
            query = query.filter(cls.model.active.is_(True))

        return cls._execute_read_query(query, detailed)