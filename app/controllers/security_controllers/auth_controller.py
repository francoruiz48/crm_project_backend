from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.security import PermissionChecker, _get_current_user
from app.db.session import get_db
from app.models.security_models import User
from app.schemas.security_schemas.auth_schema import (
    AcceptInviteRequest,
    AcceptInviteResponse,
    ChangePasswordRequest,
    InviteRequest,
    InviteResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.security_schemas.user_schema import UserResponse, UserUpdate
from app.services.security_services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])

# Hallazgo #12 (ronda de bug-hunting 2026-07-10): ningún endpoint de /auth tenía
# rate limiting, permitiendo fuerza bruta de contraseñas sin freno. Se usa una
# instancia de Limiter propia del router, mismo patrón que web_form_public_controller.py
# (slowapi lee `app.state.limiter`/el exception handler ya están montados en main.py).
limiter = Limiter(key_func=get_remote_address)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(_get_current_user)):
    """Devuelve los datos del usuario autenticado."""
    return current_user


@router.put("/me", response_model=UserResponse)
def update_me(
    data: UserUpdate,
    current_user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    """Actualiza los datos del perfil del usuario autenticado."""
    for field in ("name", "last_name", "email", "phone", "date_of_birth"):
        value = getattr(data, field, None)
        if value is not None:
            setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/register", response_model=TokenResponse)
@limiter.limit("10/minute")
def register(request: Request, data: RegisterRequest):
    """Registro público: crea cuenta + organización propia."""
    return AuthService.register(data)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, data: LoginRequest):
    """Login con email y contraseña. Devuelve access + refresh token."""
    return AuthService.login(data)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest):
    """Rota el refresh token y devuelve un nuevo par de tokens."""
    return AuthService.refresh(data.refresh_token)


@router.post("/logout")
def logout(data: RefreshRequest):
    """Revoca el refresh token (cierra sesión)."""
    return AuthService.logout(data.refresh_token)


@router.post("/invite", response_model=InviteResponse)
def invite(
    data: InviteRequest,
    current_user: User = Depends(_get_current_user),
    _perm=Depends(PermissionChecker("user:invite")),
):
    """Genera un token de invitación para agregar a alguien a una organización. Requiere permiso user:invite."""
    return AuthService.invite(
        email=data.email,
        organization_id=data.organization_id,
        current_user=current_user,
        role_code=data.role_code,
    )


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(_get_current_user),
):
    """Cambia la contraseña del usuario autenticado. Revoca todas las demás sesiones activas."""
    return AuthService.change_password(data, current_user)


@router.post("/accept-invite", response_model=AcceptInviteResponse)
def accept_invite(
    data: AcceptInviteRequest,
    current_user: User = Depends(_get_current_user),
):
    """
    Un usuario YA AUTENTICADO usa un invite_token para unirse a la organización
    indicada. Para usuarios nuevos, el alta se hace vía /auth/register
    (incluyendo invite_token en el body), no por acá.
    """
    return AuthService.accept_invite(
        invite_token=data.invite_token,
        current_user=current_user,
    )
