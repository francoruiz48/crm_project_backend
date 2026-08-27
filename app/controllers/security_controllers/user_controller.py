from typing import List, Union
from fastapi import Depends, Header, Query
from sqlalchemy.orm import Session

from app.controllers.base_controller import BaseController
from app.core.security import PermissionChecker, _get_current_user, _resolve_org_id, get_current_user_roles, require_superuser
from app.db.session import get_db
from app.models.security_models import Role, User, UserOrganization
from app.schemas.pagination_schema import PaginatedResponse
from app.schemas.security_schemas.user_schema import (
    UserDetailedResponse,
    UserPublicResponse,
    UserResponse,
    UserCreate,
    UserUpdate,
)
from app.services.security_services.user_service import UserService


class UserController(BaseController):
    router_prefix = "/users"
    service = UserService
    schema_in = UserCreate
    schema_update = UserUpdate
    schema_out = UserResponse
    schema_out_detail = UserDetailedResponse

    # Sin POST (el registro es via /auth/register)
    # Sin GET_ALL ni GET_ONE en el base — los redefinimos abajo con require_superuser
    enabled_methods = {"PUT", "DELETE", "ACTIVE"}

    relationships = [
        (User.organizations_access, UserOrganization.roles, Role.permissions)
    ]

    @classmethod
    def get_router(cls):
        router = super().get_router()

        ResponseModelItem = Union[cls.schema_out_detail, cls.schema_out]
        ResponseModelPaginated = PaginatedResponse[ResponseModelItem]

        # ---------------------------------------------------------------
        # GET ALL — requiere permiso user:view_all (solo admins de org o superadmin)
        # ---------------------------------------------------------------
        @router.get("/", response_model=ResponseModelPaginated)
        def get_all(
            page: int = Query(1, ge=1),
            page_size: int = Query(50),
            only_active: bool = True,
            detailed: bool = Query(False),
            _perm=Depends(PermissionChecker("user:view_all")),
            user_context=Depends(get_current_user_roles),
        ):
            total, items = cls.service.get_all(
                user_context=user_context,
                page=page,
                page_size=page_size,
                only_active=only_active,
                detailed=detailed,
            )
            return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)

        # ---------------------------------------------------------------
        # GET ONE — requiere permiso user:view_all
        # ---------------------------------------------------------------
        @router.get("/{obj_id}", response_model=ResponseModelItem)
        def get_one(
            obj_id: str,
            detailed: bool = Query(False),
            _perm=Depends(PermissionChecker("user:view_all")),
            user_context=Depends(get_current_user_roles),
        ):
            from fastapi import HTTPException
            obj = cls.service.get_by_id(obj_id, detailed=detailed, user_context=user_context)
            if not obj:
                raise HTTPException(status_code=404, detail="No encontrado")
            return obj

        # ---------------------------------------------------------------
        # GET /users/in-org — usuarios de la propia organización
        # Accesible para cualquier usuario autenticado que pertenezca a la org
        # ---------------------------------------------------------------
        @router.get("/in-org/members", response_model=List[UserPublicResponse])
        def get_users_in_org(
            x_organization_id_raw: str = Header(..., alias="X-Organization-Id"),
            current_user: User = Depends(_get_current_user),
            db: Session = Depends(get_db),
        ):
            from fastapi import HTTPException, status

            # Bug real encontrado 2026-07-30 (mismo de get_current_user_roles/PermissionChecker
            # en app/core/security.py): el header ya no es un int crudo desde que el frontend
            # manda org.id (public_uuid) -- ver _resolve_org_id para el detalle completo.
            x_organization_id = _resolve_org_id(db, x_organization_id_raw)
            if x_organization_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Falta o es inválido el header 'X-Organization-Id'.",
                )

            # Verificar que el usuario pertenece a la org
            membership = db.query(UserOrganization).filter_by(
                user_id=current_user.id,
                organization_id=x_organization_id,
            ).first()

            if not membership and not current_user.is_superuser:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No pertenecés a esta organización.",
                )

            # Obtener todos los user_ids de la org
            links = db.query(UserOrganization).filter_by(
                organization_id=x_organization_id,
            ).all()

            user_ids = [link.user_id for link in links]
            users = db.query(User).filter(User.id.in_(user_ids)).all()

            return [UserPublicResponse.model_validate(u) for u in users]

        # ---------------------------------------------------------------
        # Endpoints existentes de promoción
        # ---------------------------------------------------------------
        @router.patch("/promote_to_superuser/{id}", dependencies=[Depends(require_superuser)])
        async def promote_to_superuser(
            id: int,
            user_context=Depends(get_current_user_roles),
        ):
            return cls.service.promote_to_superuser(target_user_id=id, user_context=user_context)

        # Sin Depends(require_superuser) a propósito: el service ya valida
        # "superadmin O owner de ESA organización" (ver UserService.promote_to_org_owner).
        # Antes, require_superuser cortaba con 403 a cualquier no-superadmin antes de
        # que el service pudiera correr, dejando la rama de owner como código muerto
        # inalcanzable (ver hallazgos_agente/usuarios_y_permisos.md).
        @router.patch("/organization/{organization_id}/promote-owner/{user_id}")
        async def promote_to_org_owner(
            user_id: int,
            organization_id: int,
            user_context=Depends(get_current_user_roles),
        ):
            return cls.service.promote_to_org_owner(
                target_user_id=user_id,
                organization_id=organization_id,
                user_context=user_context,
            )

        return router


router = UserController.get_router()
