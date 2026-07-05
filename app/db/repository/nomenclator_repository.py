from app.core.constans import DeleteStrategy
from app.db.repository.base_repository import BaseRepository
from app.models.nomenclator import Nomenclator
from app.schemas.nomenclator_schema import NomenclatorResponse, NomenclatorDetailedResponse

class NomenclatorRepository(BaseRepository):
    model = Nomenclator
    delete_strategy = DeleteStrategy.SOFT_DELETE_ALWAYS
    schema_out = NomenclatorResponse
    schema_out_detail = NomenclatorDetailedResponse
    # El filtro base (_apply_tenant_filter) ya incluye la org admin en lecturas,
    # por lo que los nomencladores "globales" (org admin) son visibles a todas las orgs.