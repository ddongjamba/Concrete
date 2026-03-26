from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    tenant_name: str
    email: EmailStr
    password: str
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserMe(BaseModel):
    id: str
    tenant_id: str
    email: str
    role: str
    full_name: str | None

    class Config:
        from_attributes = True
