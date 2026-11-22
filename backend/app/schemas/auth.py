"""
Authentication schemas
"""
from pydantic import BaseModel, Field, EmailStr, field_validator


class UserRegistration(BaseModel):
    """Registro con contraseña de al menos 8 caracteres y máximo 72 bytes UTF-8."""
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña no puede superar 72 bytes UTF-8")
        return value


class UserLogin(BaseModel):
    """User login request"""
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    """Verify email with code"""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class ResendCodeRequest(BaseModel):
    """Resend verification code"""
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    """Request a password reset code"""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset password with emailed code."""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña no puede superar 72 bytes UTF-8")
        return value


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str


class Token(BaseModel):
    """JWT Token response"""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    full_name: str | None = None


class PendingVerification(BaseModel):
    """Response when email verification is required"""
    status: str = "pending"
    message: str


class UserResponse(BaseModel):
    """User response"""
    id: str
    email: str
    full_name: str | None = None
    currency: str = "USD"

    class Config:
        from_attributes = True


class UpdateCurrencyRequest(BaseModel):
    """Update user currency request"""
    currency: str = Field(..., pattern="^(USD|EUR|MXN|ARS|COP|CLP)$")
