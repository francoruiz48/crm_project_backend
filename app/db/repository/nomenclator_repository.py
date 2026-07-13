from app.core.constans import DeleteStrategy
from app.db.repository.base_repository import BaseRepository
from app.models.nomenclator import Nomenclator, nomenclator_parent_association
from app.schemas.nomenclator_schema import NomenclatorResponse, NomenclatorDetailedResponse

class NomenclatorRepository(BaseRepository):
    model = Nomenclator
    delete_strategy = DeleteStrategy.SOFT_DELETE_ALWAYS
    schema_out = NomenclatorResponse
    schema_out_detail = NomenclatorDetailedResponse
    # El filtro base (_apply_tenant_filter) ya incluye la org admin en lecturas,
    # por lo que los nomencladores "globales" (org admin) son visibles a todas las orgs.

    @classmethod
    def get_all(cls, session, user_context=None, only_active=True, detailed=False, base_query=None, **kwargs):
        # Feature de nomencladores dependientes (ver docs/nomencladores.md):
        # parent_nomenclator_id dejó de ser una columna simple (ahora es
        # muchos-a-muchos vía nomenclator_parent) — el filtro genérico de
        # BaseRepository.get_all (getattr(model, key) == value) ya no sirve
        # para este parámetro. Se intercepta acá y se arma el join a mano,
        # preservando el mismo nombre de query param que ya usaba el cliente.
        parent_nomenclator_id = kwargs.pop("parent_nomenclator_id", None)
        query = base_query if base_query is not None else session.query(cls.model)
        if parent_nomenclator_id is not None:
            query = query.join(
                nomenclator_parent_association,
                nomenclator_parent_association.c.nomenclator_id == cls.model.id,
            ).filter(
                nomenclator_parent_association.c.parent_nomenclator_id == int(parent_nomenclator_id)
            )
        return super().get_all(
            session, user_context=user_context, only_active=only_active,
            detailed=detailed, base_query=query, **kwargs
        )