from app.db.repository.base_repository import BaseRepository
from app.core.constans import DeleteStrategy
from app.models.team_member import TeamMember
from app.schemas.team_member_schema import TeamMemberCreate, TeamMemberDetailedResponse, TeamMemberResponse

class TeamMemberRepository(BaseRepository):
    model = TeamMember
    delete_strategy = DeleteStrategy.HARD_DELETE_ALWAYS
    schema_in = TeamMemberCreate
    schema_out = TeamMemberResponse
    schema_out_detail = TeamMemberDetailedResponse
