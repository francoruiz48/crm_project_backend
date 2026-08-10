from datetime import date, timedelta
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator

from app.core.security import normalize_email, validate_password_strength


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    # Hallazgo #13: normalizar acá para que el login sea case-insensitive
    # frente a como se guardó el email al registrarse.
    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return normalize_email(v)


class RegisterRequest(BaseModel):
    name: str
    last_name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    invite_token: Optional[str] = None  # si viene de un link de invitación, une a la org automáticamente

    # Hallazgo #13: normalizar antes de guardar, para que dos capitalizaciones
    # del mismo email no puedan registrarse como cuentas distintas.
    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("date_of_birth")
    @classmethod
    def must_be_18_or_older(cls, v: Optional[date]) -> Optional[date]:
        if v is None:
            return v
        today = date.today()
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
        if age < 18:
            raise ValueError("Debés tener al menos 18 años para registrarte.")
        return v

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, v: str) -> str:
        return validate_password_strength(v)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos hasta que expira el access token
    invite_warning: Optional[str] = None  # informativo: se completó el registro pero no se pudo unir a la org


class RefreshRequest(BaseModel):
    refresh_token: str


class InviteRequest(BaseModel):
    email: EmailStr
    # public_uuid de Organization (Fase 3). AuthService.invite() lo resuelve al id interno
    # -- bug real encontrado 2026-08-01: este campo seguía tipado `int` mientras el frontend
    # (InviteDialog.tsx) ya mandaba `activeOrg.id` (public_uuid) desde la migración Fase 3,
    # rompiendo /auth/invite con 422 para cualquier organización real. Ver AGENTS.md.
    organization_id: str
    role_code: str = "agent"  # Rol a asignar al invitado (default: agent)


class InviteResponse(BaseModel):
    invite_token: str
    expires_in_hours: int = 72
    message: str


class AcceptInviteRequest(BaseModel):
    invite_token: str


class AcceptInviteResponse(BaseModel):
    message: str
    organization_id: int


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_must_be_strong(cls, v: str) -> str:
        return validate_password_strength(v)
