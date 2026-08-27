import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.context import TENANT_ORG_ID
from app.db.session import get_db
from app.models.organization import Organization
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
# Normalización de email
# ---------------------------------------------------------------------------
# Hallazgo #13 (ronda de bug-hunting 2026-07-10): el email no se normalizaba
# antes de guardarlo/compararlo (registro y login usaban el string tal cual
# vino en el request) — dos registros con el mismo email en distinta
# capitalización (Test@x.com / test@x.com) se trataban como cuentas distintas,
# y loguearse con otra capitalización que la usada al registrarse fallaba.
# Única fuente de verdad: la usan LoginRequest/RegisterRequest/UserUpdate.
def normalize_email(email: str) -> str:
    return email.strip().lower()


# ---------------------------------------------------------------------------
# IP real del visitante detrás de un proxy (hallazgo #11, 2026-07-11)
# ---------------------------------------------------------------------------
# request.client.host es la IP del último "hop" TCP. Si el backend corre
# detrás de un proxy/load balancer (nginx, ALB, Cloudflare, el proxy que arma
# docker-compose, etc.), esa IP es la del proxy, no la del visitante real —
# todos los visitantes terminan compartiendo la misma IP a ojos del backend.
# Decisión del usuario (2026-07-11): la infraestructura de producción todavía
# no está definida, pero se asume que va a haber un proxy delante (es lo más
# probable) y se prioriza X-Forwarded-For / X-Real-IP, con fallback a
# request.client.host por si el proxy no los setea. Única fuente de verdad:
# la usan tanto el rate limiter como el `remoteip` que se le manda al
# proveedor de CAPTCHA (ambos en web_form_public_controller.py) — si cambia
# la infraestructura real, alcanza con tocar esta función.
#
# Nota de seguridad: X-Forwarded-For puede ser falsificado por un cliente
# malicioso si no hay un proxy de confianza que lo sobreescriba (o si hay
# varios proxies encadenados y no se sabe cuántos son de confianza). Mientras
# no se confirme la infraestructura real, esto es una mejora sobre el estado
# actual (todos comparten la misma IP), no una garantía anti-spoofing.
def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # El primer valor de la lista es el IP original del cliente; los
        # proxies subsiguientes van agregando el suyo a la derecha.
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


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


def _resolve_org_id(db_session: Session, raw_value: Optional[str]) -> Optional[int]:
    """
    Resuelve el valor crudo del header 'X-Organization-Id' al id interno (int).

    Bug real encontrado 2026-07-30: el header se declaraba `Optional[int]`, pero
    el frontend manda `org.id`, que desde la migración Fase 3 de
    `OrganizationResponse` es el `public_uuid` de la organización (no el id
    interno) -- excepto para la organización sintética "Panel Global"
    (SUPERUSER, id=1 literal en el frontend), que coincidía con ADMIN_ORG_ID y
    por eso nunca se notó en uso manual. FastAPI rechazaba con 422 cualquier
    otro valor (un uuid no parsea como int), rompiendo TODOS los requests de
    un usuario real que no esté parado en esa org especial. Acá aceptamos
    ambos formatos: si es numérico, se usa tal cual (compat hacia atrás /
    SUPERUSER); si no, se resuelve por `Organization.public_uuid`. Si no
    matchea nada, devuelve None (mismo comportamiento que header ausente).
    """
    if raw_value is None:
        return None
    raw_value = raw_value.strip()
    if not raw_value:
        return None
    if raw_value.lstrip("-").isdigit():
        return int(raw_value)

    row = db_session.query(Organization.id).filter(
        Organization.public_uuid == raw_value
    ).first()
    return row[0] if row else None


def get_current_user_roles(
    current_user: User = Depends(_get_current_user),
    db_session: Session = Depends(get_db),
    x_organization_id_raw: Optional[str] = Header(default=None, alias="X-Organization-Id"),
) -> UserContext:
    x_organization_id = _resolve_org_id(db_session, x_organization_id_raw)
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
        db_session: Session = Depends(get_db),
        x_organization_id_raw: Optional[str] = Header(default=None, alias="X-Organization-Id"),
    ):
        x_organization_id = _resolve_org_id(db_session, x_organization_id_raw)

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
