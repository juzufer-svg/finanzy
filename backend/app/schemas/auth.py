"""
Authentication schemas
"""
from pydantic import BaseModel, ConfigDict, Field, EmailStr


class UserRegistration(BaseModel):
    """User registration request"""
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)


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
    """Reset password with emailed code"""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=8, max_length=128)


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
    # CHG-017 (CT-002): solo informa al usuario sobre sí mismo; nunca el correo del dueño. false por defecto.
    es_dueno: bool = False

    model_config = ConfigDict(from_attributes=True)


class UpdateCurrencyRequest(BaseModel):
    """Update user currency request"""
    currency: str = Field(..., pattern="^(USD|EUR|MXN|ARS|COP|CLP)$")


class UpdateProfileRequest(BaseModel):
    """Cambiar el nombre visible (CHG-012)"""
    full_name: str = Field(..., min_length=2, max_length=100)


class ChangePasswordRequest(BaseModel):
    """Cambiar la contraseña desde el perfil (CHG-012, INV-027)"""
    actual: str = Field(..., min_length=1, max_length=128)
    nueva: str = Field(..., min_length=8, max_length=128)  # INV-018
