from fastapi import APIRouter, Depends

from app.core.security import PermissionChecker, _get_current_user
from app.models.security_models import User
from app.schemas.security_schemas.auth_schema import (
    ChangePasswordRequest,
    InviteRequest,
    InviteResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.security_services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse)
def register(data: RegisterRequest):
    """Registro público: crea cuenta + organización propia."""
    return AuthService.register(data)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest):
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


@router.post("/accept-invite", response_model=TokenResponse)
def accept_invite(invite_token: str, name: str, password: str):
    """El usuario invitado acepta la invitación y crea su cuenta (o se une si ya tiene cuenta)."""
    return AuthService.accept_invite(
        invite_token=invite_token,
        name=name,
        password=password,
    )
