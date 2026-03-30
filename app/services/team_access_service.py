from typing import Optional
from app.services.base_service import BaseService
from app.db.repository.team_access_repository import TeamWorkspaceAccessRepository, TeamCampaignAccessRepository
from fastapi import HTTPException, status
from app.core.security import UserContext

class TeamWorkspaceAccessService(BaseService):
    repository = TeamWorkspaceAccessRepository

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            # Verificar si el usuario ya está en este equipo
            existing = cls.repository.get_all(
                uow.session, 
                team_id=obj_in.team_id, 
                workspace_id=obj_in.workspace_id
            )
            if existing:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, 
                    detail=[{"field": "workspace_id", "message": "El workspace ya tiene acceso a este equipo."}]
                )
            
            data = obj_in.model_dump()
            new_member = cls.repository.create(uow.session, data, user_context=user_context)
            uow.session.flush()
            
            cls._log_audit(uow.session, new_member, action="CREATE", changes=data, user_id=user_context.user.id if user_context and user_context.user else None)
            return new_member

        return cls._execute(action="Dar acceso a Workspace", func=do_create)

class TeamCampaignAccessService(BaseService):
    repository = TeamCampaignAccessRepository

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            # Verificar si el usuario ya está en este equipo
            existing = cls.repository.get_all(
                uow.session, 
                team_id=obj_in.team_id, 
                campaign_id=obj_in.campaign_id
            )
            if existing:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, 
                    detail=[{"field": "campaign_id", "message": "La campaña ya tiene acceso a este equipo."}]
                )
            
            data = obj_in.model_dump()
            new_member = cls.repository.create(uow.session, data, user_context=user_context)
            uow.session.flush()
            
            cls._log_audit(uow.session, new_member, action="CREATE", changes=data, user_id=user_context.user.id if user_context and user_context.user else None)
            return new_member

        return cls._execute(action="Dar acceso a Campaña", func=do_create)

    