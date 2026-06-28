from datetime import date, timedelta
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    name: str
    last_name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None

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


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos hasta que expira el access token


class RefreshRequest(BaseModel):
    refresh_token: str


class InviteRequest(BaseModel):
    email: EmailStr
    organization_id: int
    role_code: str = "agent"  # Rol a asignar al invitado (default: agent)


class InviteResponse(BaseModel):
    invite_token: str
    expires_in_hours: int = 72
    message: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
