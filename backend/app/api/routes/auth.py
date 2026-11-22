"""
Authentication routes
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from app.schemas.auth import (
    UserRegistration, UserLogin, Token, UserResponse,
    VerifyEmailRequest, ResendCodeRequest, PendingVerification,
    ForgotPasswordRequest, ResetPasswordRequest, MessageResponse,
)
from app.models.user import UserDB
from app.core.security import create_access_token, verify_password
from app.core.config import settings
from app.utils.email import (
    generate_code, save_code, verify_code, send_verification_email, code_recently_sent,
)

router = APIRouter()

# ── Protección contra fuerza bruta en el login (en memoria, por correo) ───────
_MAX_LOGIN_FAILS = 5
_LOCK_MINUTES = 15
_login_fails: dict[str, dict] = {}


def _check_locked(email: str) -> None:
    entry = _login_fails.get(email)
    if entry and entry.get("locked_until") and datetime.utcnow() < entry["locked_until"]:
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {_LOCK_MINUTES} minutos.",
        )


def _register_fail(email: str) -> None:
    entry = _login_fails.get(email)
    if not entry or (entry.get("locked_until") and datetime.utcnow() >= entry["locked_until"]):
        entry = {"count": 0, "locked_until": None}
    entry["count"] += 1
    if entry["count"] >= _MAX_LOGIN_FAILS:
        entry["locked_until"] = datetime.utcnow() + timedelta(minutes=_LOCK_MINUTES)
    _login_fails[email] = entry


# ── Register ──────────────────────────────────────────────────────────────────

@router.post("/register", response_model=PendingVerification, status_code=201)
async def register(user_data: UserRegistration, background_tasks: BackgroundTasks):
    """Register a new user and send verification code to email"""
    email = user_data.email.lower()

    # Check duplicate
    existing = await UserDB.get_by_email(email)
    if existing:
        if existing["is_active"]:
            raise HTTPException(status_code=409, detail="El correo ya está registrado")
        # Already registered but pending → resend code
    else:
        # Create inactive user
        await UserDB.create(
            email=email,
            password=user_data.password,
            full_name=user_data.full_name,
            is_active=False,
        )

    # Generate & send code
    code = generate_code()
    save_code(email, code)
    background_tasks.add_task(send_verification_email, email, code)

    return PendingVerification(
        status="pending",
        message="Te enviamos un código de 6 dígitos a tu correo. Ingrésalo para activar tu cuenta.",
    )


# ── Verify email ──────────────────────────────────────────────────────────────

@router.post("/verify-email", response_model=Token)
async def verify_email(data: VerifyEmailRequest):
    """Verify email code and return JWT"""
    email = data.email.lower()

    if not verify_code(email, data.code):
        raise HTTPException(status_code=400, detail="Código inválido o expirado")

    user = await UserDB.get_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    await UserDB.activate(email)

    access_token = create_access_token(
        data={"sub": user["id"]},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=access_token, user_id=user["id"], full_name=user.get("full_name"))


# ── Resend code ───────────────────────────────────────────────────────────────

@router.post("/resend-code", response_model=PendingVerification)
async def resend_code(data: ResendCodeRequest, background_tasks: BackgroundTasks):
    """Resend verification code"""
    email = data.email.lower()
    user = await UserDB.get_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="No existe una cuenta con ese correo")

    code = generate_code()
    save_code(email, code)
    background_tasks.add_task(send_verification_email, email, code)

    return PendingVerification(
        status="pending",
        message="Te reenviamos el código a tu correo.",
    )


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(user_data: UserLogin, background_tasks: BackgroundTasks):
    """Login with email + password. Returns JWT or pending verification."""
    email = user_data.email.lower()
    _check_locked(email)
    user = await UserDB.get_by_email(email)

    if not user or not verify_password(user_data.password, user.get("hashed_password", "")):
        _register_fail(email)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    _login_fails.pop(email, None)

    if not user["is_active"]:
        # Send new verification code
        code = generate_code()
        save_code(email, code)
        background_tasks.add_task(send_verification_email, email, code)
        return PendingVerification(
            status="pending",
            message="Tu cuenta no está verificada. Te enviamos un nuevo código.",
        )

    access_token = create_access_token(
        data={"sub": user["id"]},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=access_token, user_id=user["id"])


# ── Recuperar contraseña ──────────────────────────────────────────────────────
# Los códigos de reseteo se guardan con prefijo "reset:" para no mezclarse con
# los de verificación de cuenta.

_RESET_MSG = "Si existe una cuenta con ese correo, te enviamos un código para restablecer tu contraseña."


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(data: ForgotPasswordRequest, background_tasks: BackgroundTasks):
    """Envía un código de 6 dígitos para restablecer la contraseña.
    Responde siempre lo mismo para no revelar qué correos están registrados."""
    email = data.email.lower()
    key = f"reset:{email}"
    user = await UserDB.get_by_email(email)
    if user and not code_recently_sent(key):
        code = generate_code()
        save_code(key, code)
        background_tasks.add_task(send_verification_email, email, code, "reset")
    return MessageResponse(message=_RESET_MSG)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(data: ResetPasswordRequest):
    """Cambia la contraseña si el código enviado al correo es válido."""
    email = data.email.lower()
    if not verify_code(f"reset:{email}", data.code):
        raise HTTPException(status_code=400, detail="Código inválido o expirado")

    if not await UserDB.update_password(email, data.new_password):
        raise HTTPException(status_code=400, detail="Código inválido o expirado")

    _login_fails.pop(email, None)  # desbloquear el login tras el cambio
    return MessageResponse(message="Tu contraseña fue actualizada. Ya puedes iniciar sesión.")
