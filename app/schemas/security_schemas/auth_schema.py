from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


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
