import uuid

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    org_name: str = Field(min_length=1, max_length=255)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=128)


class SignupResponse(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    user_id: uuid.UUID
    email: EmailStr
    role: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class CurrentUserResponse(BaseModel):
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    email: EmailStr
    role: str
