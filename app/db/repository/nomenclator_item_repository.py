from app.db.repository.base_repository import BaseRepository
from app.models.nomenclator_item import NomenclatorItem
from app.schemas.nomenclator_item_schema import NomenclatorItemResponse, NomenclatorItemDetailedResponse


class NomenclatorItemRepository(BaseRepository):
    model = NomenclatorItem
    schema_out = NomenclatorItemResponse
    schema_out_detail = NomenclatorItemDetailedResponse

