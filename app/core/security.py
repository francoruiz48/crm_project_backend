import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.context import TENANT_ORG_ID
from app.db.session import get_db
from app.models.security_models import User, UserOrganization

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# Política de contraseñas
# ---------------------------------------------------------------------------
# Única fuente de verdad para "contraseña segura": la usan tanto el registro
# (RegisterRequest.password) como el cambio de contraseña
# (ChangePasswordRequest.new_password). Para endurecer o relajar la regla,
# alcanza con tocar esta función — no hay que buscar duplicados en otro lado.
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 72  # bcrypt trunca (e ignora) todo lo que exceda 72 bytes


def validate_password_strength(password: str) -> str:
    """
    Exige: longitud mínima, al menos una mayúscula, una minúscula y un número.
    Pensada para usarse como @field_validator en los schemas de Pydantic:
    devuelve la contraseña si es válida, o lanza ValueError con un mensaje
    en español (el handler global lo traduce al formato estándar de error).
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"La contraseña no puede tener más de {MAX_PASSWORD_LENGTH} caracteres.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("La contraseña debe tener al menos una letra mayúscula.")
    if not re.search(r"[a-z]", password):
        raise ValueError("La contraseña debe tener al menos una letra minúscula.")
    if not re.search(r"[0-9]", password):
        raise ValueError("La contraseña debe tener al menos un número.")
    return password


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_invite_token(data: dict, expires_hours: int = 72) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    to_encode.update({"exp": expire, "type": "invite"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """Decodifica un JWT y lanza HTTPException si es inválido o expirado."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# Dependencia: usuario actual (extrae JWT del header Authorization)
# ---------------------------------------------------------------------------
def _get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, int(user_id))
    if not user or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo.",
        )
    return user


# ---------------------------------------------------------------------------
# Dependencia: solo superadmin
# ---------------------------------------------------------------------------
def require_superuser(current_user: User = Depends(_get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el superadmin puede realizar esta acción.",
        )
    return current_user


# ---------------------------------------------------------------------------
# UserContext
# ---------------------------------------------------------------------------
@dataclass
class UserContext:
    user: Any = None
    is_superuser: bool = False
    is_owner: bool = False
    organization_id: int = None
    permissions: list = field(default_factory=list)


def get_current_user_roles(
    current_user: User = Depends(_get_current_user),
    db_session: Session = Depends(get_db),
    x_organization_id: Optional[int] = Header(default=None, alias="X-Organization-Id"),
) -> UserContext:
    if x_organization_id is not None:
        TENANT_ORG_ID.set(x_organization_id)

    is_superuser = getattr(current_user, "is_superuser", False)
    is_owner_here = False

    if x_organization_id:
        user_org_link = db_session.query(UserOrganization).filter_by(
            user_id=current_user.id,
            organization_id=x_organization_id,
        ).first()
        if user_org_link and user_org_link.is_owner:
            is_owner_here = True

    permissions = (
        current_user.get_permissions(org_id=x_organization_id)
        if x_organization_id
        else []
    )

    return UserContext(
        user=current_user,
        is_superuser=is_superuser,
        is_owner=is_owner_here,
        organization_id=x_organization_id,
        permissions=permissions,
    )


# ---------------------------------------------------------------------------
# PermissionChecker
# ---------------------------------------------------------------------------
class PermissionChecker:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    async def __call__(
        self,
        user: User = Depends(_get_current_user),
        x_organization_id: Optional[int] = Header(default=None, alias="X-Organization-Id"),
    ):
        # El header es obligatorio para TODOS (incluido superadmin) para garantizar
        # el aislamiento de contexto. Sin org_id no hay contexto de operación válido.
        if not x_organization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Falta el header 'X-Organization-Id'.",
            )

        TENANT_ORG_ID.set(x_organization_id)

        # Superadmin tiene todos los permisos pero opera SIEMPRE dentro de una org
        if user.is_superuser:
            return True

        user_permissions = user.get_permissions(org_id=x_organization_id)

        if self.required_permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenés permisos para realizar esta acción en esta organización.",
            )

        return True
