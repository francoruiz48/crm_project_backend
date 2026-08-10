from typing import Optional
from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.db.repository.lead_view_repository import LeadViewRepository
from app.db.repository.team_repository import TeamRepository
from app.models.team_member import TeamMember
from app.core.security import UserContext
from app.core.constans import SystemAuditLogAction

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
        # `view` viene de repository.get_by_id(), que siempre devuelve el schema Detailed
        # (ver bug en BaseRepository.get_by_id, catalogado en backend/AGENTS.md §18-bis) --
        # ya no es el modelo ORM crudo, así que no tiene `created_by` (se sacó de
        # BaseDetailedResponse, ver comentario ahí). Se compara contra el nested `creator`
        # (uuid real) en vez del id interno viejo.
        if view.creator and view.creator.id == user_context.user.public_uuid:
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
            # obj_in.team_id llega como public_uuid de Team (Fase 3, ver backend/AGENTS.md
            # §18); se resuelve acá porque _validate_team_assignment hace un filter_by crudo
            # contra la columna interna (int). repository.create() más abajo también resuelve
            # el uuid crudo de obj_in.team_id solo (vía _resolve_fk_payload_fields), así que
            # no hace falta reasignarlo en obj_in.
            team_internal_id = None
            if obj_in.team_id:
                team_internal_id = TeamRepository.get_internal_id_by_public_uuid(uow.session, obj_in.team_id)
                if team_internal_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "team_id", "message": "El equipo especificado no existe."}]
                    )

            # Validamos integridad del equipo al crear
            cls._validate_team_assignment(uow.session, obj_in.visibility, team_internal_id, user_context)

            new_obj = cls.repository.create(uow.session, obj_in, user_context=user_context)
            uow.session.flush()
            
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, new_obj, action=SystemAuditLogAction.CREATED, changes=obj_in.model_dump(), user_id=user_id)
            
            return new_obj
            
        return cls._execute(action="Crear Lead View", func=do_create)

    @classmethod
    def update(cls, obj_id: str, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            # obj_id llega como public_uuid; se resuelve una vez al id interno.
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            # 1. Obtener la vista original (pasamos user_context para que actúe la Bóveda de lectura)
            # detailed=True explícito: _can_modify lee view.creator, que solo existe en
            # schema_out_detail (ver fix de get_by_id en base_repository.py, backend/AGENTS.md
            # §18-ter -- antes esto funcionaba de casualidad porque get_by_id ignoraba
            # detailed=False y devolvía Detailed igual).
            current_view = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context, detailed=True)
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

            # obj_in.team_id llega como public_uuid (Fase 3, ver backend/AGENTS.md §18) si
            # viene en el payload; current_view.team_id ya es el id interno (Response). Se
            # resuelve acá porque _validate_team_assignment compara contra la columna interna.
            if obj_in.team_id is not None:
                new_team_id = TeamRepository.get_internal_id_by_public_uuid(uow.session, obj_in.team_id)
                if new_team_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "team_id", "message": "El equipo especificado no existe."}]
                    )
            else:
                new_team_id = current_view.team_id

            # Si mandaron algo que altera la visibilidad, validamos el equipo
            if obj_in.visibility is not None or obj_in.team_id is not None:
                 cls._validate_team_assignment(uow.session, new_visibility, new_team_id, user_context)

            # 4. Actualizar
            updated_obj = cls.repository.update(uow.session, internal_id, obj_in, user_context=user_context)
            uow.session.flush()
            
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, updated_obj, action=SystemAuditLogAction.UPDATED, changes=obj_in.model_dump(exclude_unset=True), user_id=user_id)
            
            return updated_obj

        return cls._execute(action="Actualizar Lead View", obj_id=obj_id, func=do_update)

    @classmethod
    def delete(cls, obj_id: str, user_context: Optional[UserContext] = None, force: bool = False):
        def do_delete(uow):
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            # detailed=True explícito: _can_modify lee view.creator, que solo existe en
            # schema_out_detail (ver fix de get_by_id en base_repository.py, backend/AGENTS.md
            # §18-ter -- antes esto funcionaba de casualidad porque get_by_id ignoraba
            # detailed=False y devolvía Detailed igual).
            current_view = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context, detailed=True)
            if not current_view:
                cls._not_found(obj_id)

            # Verificar permisos de BORRADO
            if not cls._can_modify(uow.session, current_view, user_context):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tienes permisos para eliminar esta vista."
                )

            result = cls.repository.delete(uow.session, internal_id, user_context=user_context)
            
            user_id = user_context.user.id if user_context and user_context.user else None
            # internal_id explícito: si el borrado fue físico, la fila ya no está para resolver
            # uuid->id por query (ver backend/AGENTS.md §18-octies).
            cls._log_audit(uow.session, current_view, action=SystemAuditLogAction.DELETED, changes=None, user_id=user_id, internal_id=internal_id)
            
            return result

        return cls._execute(action="Eliminando Lead View", obj_id=obj_id, func=do_delete)