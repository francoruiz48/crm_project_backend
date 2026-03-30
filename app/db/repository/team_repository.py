from app.db.repository.base_repository import BaseRepository
from app.models.team import Team
from app.schemas.team_schema import TeamCreate, TeamDetailedResponse, TeamResponse

class TeamRepository(BaseRepository):
    model = Team
    schema_in = TeamCreate
    schema_out = TeamResponse
    schema_out_detail = TeamDetailedResponse
