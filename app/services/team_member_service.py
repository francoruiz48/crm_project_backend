from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.db.repository.team_member_repository import TeamMemberRepository

class TeamMemberService(BaseService):
    repository = TeamMemberRepository

    @classmethod
    def create(cls, obj_in, created_by=None):
        def do_create(uow):
            # Verificar si el usuario ya está en este equipo
            existing = cls.repository.get_all(
                uow.session, 
                team_id=obj_in.team_id, 
                user_id=obj_in.user_id
            )
            if existing:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, 
                    detail=[{"field": "user_id", "message": "El usuario ya pertenece a este equipo."}]
                )
            
            data = obj_in.model_dump()
            new_member = cls.repository.create(uow.session, data, created_by)
            uow.session.flush()
            
            cls._log_audit(uow.session, new_member, action="CREATE", changes=data, user_id=created_by)
            return new_member

        return cls._execute(action="Agregar Miembro", func=do_create)