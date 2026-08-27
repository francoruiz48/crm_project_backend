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
            # parent_item_id llega como public_uuid de NomenclatorItem (Fase 3, el frontend
            # nunca conoce el id interno -- ver nomenclatorService.ts). Bug real encontrado
            # 2026-08-04: antes se hacía int(parent_item_id) directo, sin resolver -- tiraba
            # ValueError sin capturar (500) en CUALQUIER llamada real (LeadPartialUpdate.tsx/
            # LeadFormMultipleFields.tsx siempre mandan el uuid del ítem padre elegido). El
            # resolver genérico de FKs (resolve_fk_filter_value) no aplica acá porque esto no
            # es una columna real de cls.model, es una relación M2M autorreferencial -- se
            # resuelve a mano contra el propio modelo. Ver backend/AGENTS.md.
            if str(parent_item_id).lstrip("-").isdigit():
                parent_item_id_internal = int(parent_item_id)
            else:
                parent_item_id_internal = cls.get_internal_id_by_public_uuid(session, parent_item_id)
            query = query.join(
                nomenclator_item_parent_association,
                nomenclator_item_parent_association.c.item_id == cls.model.id,
            ).filter(
                nomenclator_item_parent_association.c.parent_item_id == parent_item_id_internal
            )
        return super().get_all(
            session, user_context=user_context, only_active=only_active,
            detailed=detailed, base_query=query, **kwargs
        )

