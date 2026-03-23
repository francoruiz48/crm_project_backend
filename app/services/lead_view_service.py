from typing import Optional
from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.db.repository.lead_view_repository import LeadViewRepository
from app.models.team_member import TeamMember
from app.core.security import UserContext

class LeadViewService(BaseService):
    repository = LeadViewRepository

    @classmethod
    def _can_modify(cls, session, view, user_context: UserContext) -> bool:
        """
        Define quién tiene derecho a editar o borrar una vista.
        """
        if not user_context or not user_context.user:
            return False

        # 1. Los Dioses del sistema (Soporte o Administradores de la Empresa)
        if user_context.is_superuser or user_context.is_owner:
            return True
            
        user_id = user_context.user.id

        # 2. El Creador original siempre puede
        if view.created_by == user_id:
            return True
            
        # 3. Si es de Equipo, los Mánagers de ese equipo pueden
        if view.visibility == "TEAM" and view.team_id:
            manager_membership = session.query(TeamMember).filter_by(
                team_id=view.team_id, 
                user_id=user_id, 
                role="MANAGER"
            ).first()
            if manager_membership:
                return True
                
        return False

    @classmethod
    def _validate_team_assignment(cls, session, visibility: str, team_id: int, user_context: UserContext):
        """
        Valida que si se asigna a un TEAM, el ID venga y el usuario pertenezca a ese equipo.
        """
        if visibility == "TEAM":
            if not team_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "team_id", "message": "Debe especificar un equipo para una vista TEAM."}]
                )
            
            # Validamos que el usuario pertenezca al equipo (a menos que sea Admin)
            if user_context and not (user_context.is_superuser or user_context.is_owner):
                membership = session.query(TeamMember).filter_by(team_id=team_id, user_id=user_context.user.id).first()
                if not membership:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=[{"field": "team_id", "message": "No puedes asignar una vista a un equipo al que no perteneces."}]
                    )
        elif team_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=[{"field": "team_id", "message": "No se debe enviar team_id si la visibilidad no es TEAM."}]
            )

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            # Validamos integridad del equipo al crear
            cls._validate_team_assignment(uow.session, obj_in.visibility, obj_in.team_id, user_context)
            
            new_obj = cls.repository.create(uow.session, obj_in, user_context=user_context)
            uow.session.flush()
            
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, new_obj, action="CREATE", changes=obj_in.model_dump(), user_id=user_id)
            
            return new_obj
            
        return cls._execute(action="Crear Lead View", func=do_create)

    @classmethod
    def update(cls, obj_id: int, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            # 1. Obtener la vista original (pasamos user_context para que actúe la Bóveda de lectura)
            current_view = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context, detailed=False)
            if not current_view:
                cls._not_found(obj_id)

            # 2. Verificar permisos de EDICIÓN (Regla de negocio)
            if not cls._can_modify(uow.session, current_view, user_context):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tienes permisos para editar esta vista. Solo el creador, un mánager del equipo o un administrador pueden hacerlo."
                )

            # 3. Validar si están intentando cambiar la visibilidad o el equipo
            new_visibility = obj_in.visibility if obj_in.visibility is not None else current_view.visibility
            new_team_id = obj_in.team_id if obj_in.team_id is not None else current_view.team_id
            
            # Si mandaron algo que altera la visibilidad, validamos el equipo
            if obj_in.visibility is not None or obj_in.team_id is not None:
                 cls._validate_team_assignment(uow.session, new_visibility, new_team_id, user_context)
            
            # 4. Actualizar
            updated_obj = cls.repository.update(uow.session, obj_id, obj_in, user_context=user_context)
            uow.session.flush()
            
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, updated_obj, action="UPDATE", changes=obj_in.model_dump(exclude_unset=True), user_id=user_id)
            
            return updated_obj

        return cls._execute(action="Actualizar Lead View", obj_id=obj_id, func=do_update)

    @classmethod
    def delete(cls, obj_id: int, user_context: Optional[UserContext] = None):
        def do_delete(uow):
            current_view = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context, detailed=False)
            if not current_view:
                cls._not_found(obj_id)

            # Verificar permisos de BORRADO
            if not cls._can_modify(uow.session, current_view, user_context):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tienes permisos para eliminar esta vista."
                )
                
            result = cls.repository.delete(uow.session, obj_id, user_context=user_context)
            
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, current_view, action="DELETE", changes=None, user_id=user_id)
            
            return result

        return cls._execute(action="Eliminando Lead View", obj_id=obj_id, func=do_delete)