"""
Authentication schemas with input validation.
"""
from pydantic import BaseModel, Field, EmailStr, field_validator


def _validate_bcrypt_password(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("La contraseña no puede superar 72 bytes UTF-8")
    return value


class UserRegistration(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_bcrypt_password(value)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_bcrypt_password(value)


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResendCodeRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_bcrypt_password(value)


class MessageResponse(BaseModel):
    message: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    full_name: str | None = None


class PendingVerification(BaseModel):
    status: str = "pending"
    message: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    currency: str = "USD"

    class Config:
        from_attributes = True


class UpdateCurrencyRequest(BaseModel):
    currency: str = Field(..., pattern="^(USD|EUR|MXN|ARS|COP|CLP)$")
