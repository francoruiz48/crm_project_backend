import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from app.core.constans import ADMIN_ORG_ID
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_invite_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.unit_of_work import UnitOfWork
from app.models.organization import Organization
from app.models.refresh_token_model import RefreshToken
from app.models.security_models import Role, User, UserOrganization
from app.schemas.security_schemas.auth_schema import (
    ChangePasswordRequest,
    InviteResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)


def _hash_refresh_token(raw_token: str) -> str:
    """Hashea el refresh token antes de guardarlo en la DB."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


# Hash dummy pre-computado para usar en el timing-attack fix del login.
# Se genera una sola vez al cargar el módulo para no añadir latencia por request.
_DUMMY_HASH = hash_password("__dummy_timing_prevention__")


def _build_token_response(user: User, session: Session) -> TokenResponse:
    """Genera el par access + refresh token y persiste el refresh en la DB."""
    # --- Access token ---
    access_token = create_access_token(data={"sub": str(user.id)})

    # --- Refresh token ---
    raw_refresh = secrets.token_urlsafe(64)
    token_hash = _hash_refresh_token(raw_refresh)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    db_refresh = RefreshToken(
        token_hash=token_hash,
        user_id=user.id,
        expires_at=expires_at,
        revoked=False,
    )
    session.add(db_refresh)

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


class AuthService:

    @classmethod
    def register(cls, data: RegisterRequest) -> TokenResponse:
        def do_register(uow: UnitOfWork):
            # 1. Verificar que el email no exista
            existing = uow.session.query(User).filter_by(email=data.email).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ya existe una cuenta con ese email.",
                )

            # 2. Crear el usuario
            new_user = User(
                name=data.name,
                email=data.email,
                hashed_password=hash_password(data.password),
                is_superuser=False,
            )
            uow.session.add(new_user)
            uow.session.flush()

            return _build_token_response(new_user, uow.session)

        with UnitOfWork() as uow:
            result = do_register(uow)
        return result

    @classmethod
    def login(cls, data: LoginRequest) -> TokenResponse:
        with UnitOfWork() as uow:
            user = uow.session.query(User).filter_by(email=data.email).first()

            # Siempre ejecutamos bcrypt para evitar timing attacks:
            # si el usuario no existe usamos un hash dummy pre-computado,
            # así el tiempo de respuesta es igual para emails válidos e inválidos.
            candidate_hash = user.hashed_password if (user and user.hashed_password) else _DUMMY_HASH
            password_ok = verify_password(data.password, candidate_hash)

            if not user or not user.hashed_password or not password_ok:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales incorrectas.",
                )

            if not user.active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tu cuenta está desactivada.",
                )

            return _build_token_response(user, uow.session)

    @classmethod
    def refresh(cls, raw_refresh_token: str) -> TokenResponse:
        token_hash = _hash_refresh_token(raw_refresh_token)

        with UnitOfWork() as uow:
            db_token = uow.session.query(RefreshToken).filter_by(
                token_hash=token_hash
            ).first()

            if not db_token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token inválido.",
                )

            if db_token.revoked:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token revocado.",
                )

            if db_token.expires_at < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token expirado.",
                )

            # Rotación: revocar el viejo y emitir uno nuevo
            db_token.revoked = True
            uow.session.flush()

            user = uow.session.get(User, db_token.user_id)
            if not user or not user.active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario no encontrado o inactivo.",
                )

            return _build_token_response(user, uow.session)

    @classmethod
    def logout(cls, raw_refresh_token: str) -> dict:
        token_hash = _hash_refresh_token(raw_refresh_token)

        with UnitOfWork() as uow:
            db_token = uow.session.query(RefreshToken).filter_by(
                token_hash=token_hash
            ).first()

            if db_token and not db_token.revoked:
                db_token.revoked = True

        return {"message": "Sesión cerrada correctamente."}

    @classmethod
    def invite(cls, email: str, organization_id: int, current_user: User, role_code: str = "agent") -> InviteResponse:
        """
        Genera un token de invitación para que alguien se una a una organización.
        El frontend usa este token para redirigir al usuario al flujo de registro/aceptación.
        """
        with UnitOfWork() as uow:
            # Verificar que el que invita pertenece a la org
            membership = uow.session.query(UserOrganization).filter_by(
                user_id=current_user.id,
                organization_id=organization_id,
            ).first()

            if not membership and not current_user.is_superuser:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No pertenecés a esta organización.",
                )

            org = uow.session.get(Organization, organization_id)
            if not org:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Organización no encontrada.",
                )

            org_name = org.name  # capturar antes de que la sesión se cierre

            # Verificar que el rol existe (primero org-específico, luego global como fallback)
            role = (
                uow.session.query(Role).filter_by(code=role_code, organization_id=organization_id).first()
                or uow.session.query(Role).filter_by(code=role_code, organization_id=ADMIN_ORG_ID).first()
            )
            if not role:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El rol '{role_code}' no existe.",
                )

        invite_token = create_invite_token(
            data={
                "email": email,
                "org_id": organization_id,
                "invited_by": current_user.id,
                "role_code": role_code,
            }
        )

        return InviteResponse(
            invite_token=invite_token,
            expires_in_hours=72,
            message=f"Compartí este token con {email} para que pueda unirse a '{org_name}'.",
        )

    @classmethod
    def change_password(cls, data: ChangePasswordRequest, current_user: User) -> dict:
        """
        Cambia la contraseña del usuario autenticado.
        - Verifica la contraseña actual antes de aceptar la nueva.
        - Revoca todos los refresh tokens activos (fuerza logout de otras sesiones).
        - Usa tiempo de respuesta constante para no filtrar si el password es correcto.
        """
        MIN_PASSWORD_LENGTH = 8

        if len(data.new_password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La nueva contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.",
            )

        with UnitOfWork() as uow:
            user = uow.session.get(User, current_user.id)

            if not user or not user.hashed_password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No se puede cambiar la contraseña de esta cuenta.",
                )

            # Verificación con tiempo constante: siempre corre bcrypt
            if not verify_password(data.current_password, user.hashed_password):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La contraseña actual es incorrecta.",
                )

            # Actualizar contraseña
            user.hashed_password = hash_password(data.new_password)

            # Revocar todos los refresh tokens activos (cierra otras sesiones)
            uow.session.query(RefreshToken).filter_by(
                user_id=user.id, revoked=False
            ).update({"revoked": True})

            uow.session.flush()

        return {"message": "Contraseña actualizada correctamente. Las demás sesiones fueron cerradas."}

    @classmethod
    def accept_invite(cls, invite_token: str, name: str, password: str) -> TokenResponse:
        """
        El usuario invitado usa el token para crear su cuenta y unirse a la org.
        Si ya tiene cuenta, solo lo agrega a la org.
        """
        payload = decode_token(invite_token)

        if payload.get("type") != "invite":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token de invitación inválido.",
            )

        email = payload.get("email")
        org_id = payload.get("org_id")

        with UnitOfWork() as uow:
            user = uow.session.query(User).filter_by(email=email).first()

            if not user:
                # Crear cuenta nueva
                user = User(
                    name=name,
                    email=email,
                    hashed_password=hash_password(password),
                    is_superuser=False,
                )
                uow.session.add(user)
                uow.session.flush()

            # Agregar a la org si no está ya
            existing_link = uow.session.query(UserOrganization).filter_by(
                user_id=user.id,
                organization_id=org_id,
            ).first()

            if not existing_link:
                membership = UserOrganization(
                    user_id=user.id,
                    organization_id=org_id,
                    is_owner=False,
                )
                uow.session.add(membership)
                uow.session.flush()

                # Asignar el rol de la org especificado en el token (default: agent)
                role_code = payload.get("role_code", "agent")
                org_role = uow.session.query(Role).filter_by(
                    code=role_code, organization_id=org_id
                ).first()
                if org_role:
                    membership.roles = [org_role]

                uow.session.flush()

            return _build_token_response(user, uow.session)
