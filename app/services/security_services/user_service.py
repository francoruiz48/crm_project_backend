from app.services.base_service import BaseService
from app.db.repository.security_repositories.user_repository import UserRepository
from app.models.security_models import User, UserOrganization
from fastapi import HTTPException, status
from app.core.security import UserContext

class UserService(BaseService):
    repository = UserRepository


    @classmethod
    def promote_to_superuser(cls, target_user_id: int, user_context: UserContext):
        """
        Otorga acceso de Super Admin global. SOLO un Super Admin actual puede hacer esto.
        """
        def do_promote(uow):
            if not user_context or not user_context.is_superuser:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo un Super Administrador puede otorgar este rol."
                )

            target_user = uow.session.get(User, target_user_id)
            if not target_user:
                cls._not_found(target_user_id)

            target_user.is_superuser = True
            
            cls._log_audit(uow.session, target_user, action="PROMOTE_SUPERUSER", changes={"is_superuser": True}, user_id=user_context.user.id)
            return target_user

        return cls._execute(action="Promover a Super usuario", obj_id=target_user_id, func=do_promote)

    @classmethod
    def promote_to_org_owner(cls, target_user_id: int, organization_id: int, user_context: UserContext):
        """
        Convierte a un usuario en Owner de una Organización.
        SOLO un Super Admin o un Owner actual de ESA organización puede hacerlo.
        """
        def do_promote(uow):
            # 1. Validación de seguridad estricta
            has_permission = False
            if user_context and user_context.is_superuser:
                has_permission = True
            elif user_context and user_context.is_owner:
                # Verificamos si es owner en LA MISMA organización donde quiere promover a otro
                from app.core.context import TENANT_ORG_ID
                if TENANT_ORG_ID.get() == organization_id:
                    has_permission = True

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tienes permisos para designar a un administrador en esta organización."
                )

            # 2. Buscar o crear la relación en UserOrganization
            link = uow.session.query(UserOrganization).filter_by(
                user_id=target_user_id, 
                organization_id=organization_id
            ).first()

            if not link:
                # Si el usuario no estaba en la org, lo agregamos como owner
                link = UserOrganization(user_id=target_user_id, organization_id=organization_id, is_owner=True)
                uow.session.add(link)
            else:
                # Si ya estaba, simplemente le subimos el privilegio
                link.is_owner = True

            uow.session.flush()

            cls._log_audit(uow.session, link, action="PROMOTE_OWNER", changes={"is_owner": True}, user_id=user_context.user.id)
            return link

        return cls._execute(action="Promover a Propietario", obj_id=target_user_id, func=do_promote)
