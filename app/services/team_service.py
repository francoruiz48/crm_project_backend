from app.services.base_service import BaseService
from app.db.repository.team_repository import TeamRepository

class TeamService(BaseService):
    repository = TeamRepository

    