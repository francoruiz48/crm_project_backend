from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.team import Team
from app.schemas.team_schema import TeamCreate, TeamDetailedResponse, TeamResponse

class TeamRepository(BaseRepository):
    model = Team
    delete_strategy = DeleteStrategy.SOFT_DELETE_HARD_OPT
    schema_in = TeamCreate
    schema_out = TeamResponse
    schema_out_detail = TeamDetailedResponse
