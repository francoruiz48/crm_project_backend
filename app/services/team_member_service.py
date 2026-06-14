from typing import Optional
from fastapi import HTTPException, status
from app.core.security import UserContext
from app.db.repository.team_member_repository import TeamMemberRepository
from app.models.team import Team
from app.models.team_member import TeamMember
from app.services.base_service import BaseService
from app.core.constans import SystemAuditLogAction
 
 
def _caller_role(session, user_context, team_id: int) -> str:
    """MANAGER | AGENT | NONE"""
    if not user_context or not user_context.user:
        return "NONE"
    if user_context.is_superuser or user_context.is_owner:
        return "MANAGER"
    m = session.query(TeamMember).filter_by(
        team_id=team_id, user_id=user_context.user.id
    ).first()
    return m.role if m else "NONE"
 
 
class TeamMemberService(BaseService):
    repository = TeamMemberRepository
 
    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            from app.core.context import TENANT_ORG_ID
            org_id     = TENANT_ORG_ID.get()
            team_id    = obj_in.team_id
            target_uid = obj_in.user_id
            role       = obj_in.role
 
            team = uow.session.query(Team).filter_by(id=team_id).first()
            if not team:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "team_id", "message": f"El equipo ID={team_id} no existe."}])
            if org_id and team.organization_id != org_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "team_id", "message": "El equipo no pertenece a esta organización."}])
 
            if uow.session.query(TeamMember).filter_by(team_id=team_id, user_id=target_uid).first():
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "user_id", "message": "El usuario ya pertenece a este equipo."}])
 
            caller = _caller_role(uow.session, user_context, team_id)
 
            if caller == "NONE":
                raise HTTPException(status.HTTP_403_FORBIDDEN,
                    detail="No tenés permisos para agregar miembros a este equipo.")
            if caller == "AGENT":
                raise HTTPException(status.HTTP_403_FORBIDDEN,
                    detail="Un AGENT no puede agregar miembros al equipo. Solicitá a un MANAGER que lo haga.")
            if role == "MANAGER" and caller != "MANAGER":
                raise HTTPException(status.HTTP_403_FORBIDDEN,
                    detail="Solo un MANAGER del equipo puede promover a otro miembro como MANAGER.")
 
            # AGENT no puede auto-promoverse
            if (user_context and user_context.user and
                    target_uid == user_context.user.id and role == "MANAGER" and caller == "AGENT"):
                raise HTTPException(status.HTTP_403_FORBIDDEN,
                    detail="Un AGENT no puede asignarse a sí mismo como MANAGER del equipo.")
 
            data       = obj_in.model_dump()
            new_member = cls.repository.create(uow.session, data, user_context=user_context)
            uow.session.flush()
            cls._log_audit(uow.session, new_member, action=SystemAuditLogAction.CREATED, changes=data,
                           user_id=user_context.user.id if user_context and user_context.user else None)
            return new_member
 
        return cls._execute(action="Agregar Miembro al Equipo", func=do_create)
 
    @classmethod
    def update(cls, obj_id: int, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            member = uow.session.query(TeamMember).filter_by(id=obj_id).first()
            if not member:
                cls._not_found(obj_id)
            data     = obj_in.model_dump(exclude_unset=True)
            new_role = data.get("role")
            if new_role:
                caller = _caller_role(uow.session, user_context, member.team_id)
                if caller != "MANAGER":
                    raise HTTPException(status.HTTP_403_FORBIDDEN,
                        detail="Solo un MANAGER del equipo puede modificar roles.")
                if (new_role == "MANAGER" and user_context and user_context.user and
                        member.user_id == user_context.user.id and caller == "AGENT"):
                    raise HTTPException(status.HTTP_403_FORBIDDEN,
                        detail="Un AGENT no puede asignarse a sí mismo como MANAGER del equipo.")
 
            changes = {k: {"old": getattr(member, k, None), "new": v}
                       for k, v in data.items()
                       if hasattr(member, k) and getattr(member, k) != v}
 
            updated = cls.repository.update(uow.session, obj_id, data, user_context=user_context)
            uow.session.flush()
            if changes:
                cls._log_audit(uow.session, updated, action=SystemAuditLogAction.UPDATED, changes=changes,
                               user_id=user_context.user.id if user_context and user_context.user else None)
            return updated
 
        return cls._execute(action="Actualizar Miembro", obj_id=obj_id, func=do_update)

    @classmethod
    def delete(cls, obj_id: int, user_context: Optional[UserContext] = None, force: bool = False):
        def do_delete(uow):
            member = uow.session.query(TeamMember).filter_by(id=obj_id).first()
            if not member:
                cls._not_found(obj_id)

            caller = _caller_role(uow.session, user_context, member.team_id)
            if caller != "MANAGER":
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail="Solo un MANAGER del equipo puede eliminar miembros.",
                )

            cls._log_audit(uow.session, member, action=SystemAuditLogAction.DELETED, changes=None,
                           user_id=user_context.user.id if user_context and user_context.user else None)
            uow.session.delete(member)
            uow.session.flush()
            return {"detail": f"TeamMember({obj_id}) eliminado correctamente."}

        return cls._execute(action="Eliminar Miembro del Equipo", obj_id=obj_id, func=do_delete)