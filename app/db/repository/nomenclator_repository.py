from app.db.repository.base_repository import BaseRepository
from app.models.nomenclator import Nomenclator
from app.schemas.nomenclator_schema import NomenclatorResponse


class NomenclatorRepository(BaseRepository):
    model = Nomenclator
    schema_out = NomenclatorResponse


