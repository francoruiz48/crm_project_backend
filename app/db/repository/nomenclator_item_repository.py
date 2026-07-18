from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.nomenclator_item import NomenclatorItem, nomenclator_item_parent_association
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse, NomenclatorItemDetailedResponse


class NomenclatorItemRepository(BaseRepository):
    model = NomenclatorItem
    delete_strategy = DeleteStrategy.SOFT_DELETE_ALWAYS
    schema_out = NomenclatorItemResponse
    schema_out_detail = NomenclatorItemDetailedResponse

    @classmethod
    def get_all(cls, session, user_context=None, only_active=True, detailed=False, base_query=None, **kwargs):
        # Feature de nomencladores dependientes (ver docs/nomencladores.md):
        # parent_item_id dejó de ser una columna simple (ahora es
        # muchos-a-muchos vía nomenclator_item_parent) — mismo motivo y mismo
        # patrón que NomenclatorRepository.get_all. Este filtro es el que
        # alimenta los combos en cascada del frontend
        # (GET /nomenclator_items/?nomenclator_id=X&parent_item_id=Y), así que
        # el nombre del query param se mantiene igual a propósito.
        parent_item_id = kwargs.pop("parent_item_id", None)
        query = base_query if base_query is not None else session.query(cls.model)
        if parent_item_id is not None:
            query = query.join(
                nomenclator_item_parent_association,
                nomenclator_item_parent_association.c.item_id == cls.model.id,
            ).filter(
                nomenclator_item_parent_association.c.parent_item_id == int(parent_item_id)
            )
        return super().get_all(
            session, user_context=user_context, only_active=only_active,
            detailed=detailed, base_query=query, **kwargs
        )

