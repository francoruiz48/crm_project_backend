from typing import Optional
from fastapi import HTTPException, status
from app.core.security import UserContext
from app.db.repository.team_repository import TeamRepository
from app.db.repository.team_member_repository import TeamMemberRepository
from app.models.team import Team
from app.models.team_member import TeamMember
from app.services.base_service import BaseService


class TeamService(BaseService):
    repository = TeamRepository
    member_repository = TeamMemberRepository

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            from app.core.context import TENANT_ORG_ID
            org_id = TENANT_ORG_ID.get()
            data   = obj_in.model_dump(exclude_unset=True)
 
            # Nombre único por organización
            existing = uow.session.query(Team).filter_by(
                name=data.get("name"),
                organization_id=org_id,
            ).filter(Team.active.is_(True)).first()
 
            if existing:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=[{
                        "field": "name",
                        "message": f"Ya existe un equipo activo llamado \'{data.get('name')}\' en esta organización."
                    }]
                )
 
            new_team = cls.repository.create(uow.session, data, user_context=user_context)
            uow.session.flush()
 
            # Agregar al creador como MANAGER automáticamente
            if user_context and user_context.user:
                uow.session.add(TeamMember(
                    team_id    = new_team.id,
                    user_id    = user_context.user.id,
                    role       = "MANAGER",
                    created_by = user_context.user.id,
                ))
                uow.session.flush()
 
            cls._log_audit(uow.session, new_team, action="CREATE", changes=data,
                           user_id=user_context.user.id if user_context and user_context.user else None)
            return new_team
 
        return cls._execute(action="Crear Equipo", func=do_create)