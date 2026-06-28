from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.tag import Tag
from app.schemas.tag_schema import TagResponse, TagDetailedResponse

class TagRepository(BaseRepository):
    model = Tag
    delete_strategy = DeleteStrategy.HARD_DELETE_ALWAYS
    schema_out = TagResponse
    schema_out_detail = TagDetailedResponse