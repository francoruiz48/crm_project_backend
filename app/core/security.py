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
        if x_organization_id is not None:
            TENANT_ORG_ID.set(x_organization_id)

        if user.is_superuser:
            return True

        if not x_organization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Falta el header 'X-Organization-Id' para verificar los permisos en este contexto.",
            )

        user_permissions = user.get_permissions(org_id=x_organization_id)

        if self.required_permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tienes permisos en esta organización. Requiere: {self.required_permission}",
            )

        return True
