"""
Authentication routes
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from app.schemas.auth import (
    UserRegistration, UserLogin, Token,
    VerifyEmailRequest, ResendCodeRequest, PendingVerification,
    ForgotPasswordRequest, ResetPasswordRequest, MessageResponse,
)
from app.models.user import UserDB
from app.core.security import create_access_token, verify_password
from app.core.config import settings
from app.core.rate_limit import SlidingWindow, client_ip, enforce
from app.utils.email import (
    generate_code, save_code, verify_code, send_verification_email, code_recently_sent,
)

router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Protección contra fuerza bruta en el login (en memoria, por correo) ───────
_MAX_LOGIN_FAILS = 5
_LOCK_MINUTES = 15
_login_fails: dict[str, dict] = {}


def _check_locked(email: str) -> None:
    entry = _login_fails.get(email)
    if entry and entry.get("locked_until") and _utcnow() < entry["locked_until"]:
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {_LOCK_MINUTES} minutos.",
        )


def _register_fail(email: str) -> None:
    entry = _login_fails.get(email)
    if not entry or (entry.get("locked_until") and _utcnow() >= entry["locked_until"]):
        entry = {"count": 0, "locked_until": None}
    entry["count"] += 1
    if entry["count"] >= _MAX_LOGIN_FAILS:
        entry["locked_until"] = _utcnow() + timedelta(minutes=_LOCK_MINUTES)
    _login_fails[email] = entry


# ── Límites de envío de códigos por correo ────────────────────────────────────
# Evitan que un script agote el cupo diario de Brevo (300 correos/día en el plan
# gratis) o use la app para enviar correos a direcciones ajenas.
CODE_RESEND_SECONDS = 60                                      # mínimo entre códigos al mismo correo
_ip_email_requests = SlidingWindow(limit=10, window_seconds=3600)    # pedidos de código por IP/hora
_email_daily = SlidingWindow(limit=10, window_seconds=86400)        # correos al mismo destinatario/día
_global_daily = SlidingWindow(limit=250, window_seconds=86400)      # total de correos/día (margen bajo 300)

# Intentos de credenciales/códigos por IP (complementa el bloqueo por correo)
_ip_auth_attempts = SlidingWindow(limit=30, window_seconds=600)

_TOO_MANY = "Demasiadas solicitudes. Espera unos minutos e intenta de nuevo."


def _limit_ip_for_email(request: Request) -> None:
    enforce(_ip_email_requests, client_ip(request), _TOO_MANY)


def _limit_ip_for_auth(request: Request) -> None:
    enforce(_ip_auth_attempts, client_ip(request), _TOO_MANY)


def _issue_code(
    code_key: str, to_email: str, purpose: str, background_tasks: BackgroundTasks
) -> str:
    """Genera y envía un código respetando los límites.

    Devuelve:
      "sent"     → se envió un código nuevo
      "recent"   → ya se envió uno hace menos de CODE_RESEND_SECONDS (sigue válido)
      "limited"  → se alcanzó el límite diario (por destinatario o global)
    """
    if code_recently_sent(code_key, CODE_RESEND_SECONDS):
        return "recent"
    if not _email_daily.allowed(to_email) or not _global_daily.allowed("all"):
        if not _global_daily.allowed("all"):
            print("[EMAIL LIMIT] Se alcanzó el límite global diario de correos")
        return "limited"
    _email_daily.hit(to_email)
    _global_daily.hit("all")
    code = generate_code()
    save_code(code_key, code)
    background_tasks.add_task(send_verification_email, to_email, code, purpose)
    return "sent"


_LIMITED_MSG = "Ya enviamos varios códigos a este correo hoy. Revisa tu bandeja (y spam) o intenta mañana."


# ── Register ──────────────────────────────────────────────────────────────────

@router.post("/register", response_model=PendingVerification, status_code=201)
async def register(user_data: UserRegistration, request: Request, background_tasks: BackgroundTasks):
    """Register a new user and send verification code to email"""
    _limit_ip_for_email(request)
    email = user_data.email.lower()

    existing = await UserDB.get_by_email(email)
    if existing:
        if existing["is_active"]:
            raise HTTPException(status_code=409, detail="El correo ya está registrado")
        # Ya registrado pero pendiente → se reenvía el código (con límites)
    else:
        await UserDB.create(
            email=email,
            password=user_data.password,
            full_name=user_data.full_name,
            is_active=False,
        )

    if _issue_code(email, email, "verify", background_tasks) == "limited":
        raise HTTPException(status_code=429, detail=_LIMITED_MSG)

    return PendingVerification(
        status="pending",
        message="Te enviamos un código de 6 dígitos a tu correo. Ingrésalo para activar tu cuenta.",
    )


# ── Verify email ──────────────────────────────────────────────────────────────

@router.post("/verify-email", response_model=Token)
async def verify_email(data: VerifyEmailRequest, request: Request):
    """Verify email code and return JWT"""
    _limit_ip_for_auth(request)
    email = data.email.lower()

    if not verify_code(email, data.code):
        raise HTTPException(status_code=400, detail="Código inválido o expirado")

    user = await UserDB.get_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    await UserDB.activate(email)

    access_token = create_access_token(
        data={"sub": user["id"], "sv": user.get("session_version", 0)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=access_token, user_id=user["id"], full_name=user.get("full_name"))


# ── Resend code ───────────────────────────────────────────────────────────────

@router.post("/resend-code", response_model=PendingVerification)
async def resend_code(data: ResendCodeRequest, request: Request, background_tasks: BackgroundTasks):
    """Reenvía el código de verificación de una cuenta pendiente.
    Responde lo mismo exista o no la cuenta, para no revelar qué correos están registrados."""
    _limit_ip_for_email(request)
    email = data.email.lower()
    user = await UserDB.get_by_email(email)

    if user and not user["is_active"]:
        if _issue_code(email, email, "verify", background_tasks) == "limited":
            raise HTTPException(status_code=429, detail=_LIMITED_MSG)

    return PendingVerification(
        status="pending",
        message="Si tu cuenta está pendiente de verificación, te enviamos un código a tu correo.",
    )


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(user_data: UserLogin, request: Request, background_tasks: BackgroundTasks):
    """Login with email + password. Returns JWT or pending verification."""
    _limit_ip_for_auth(request)
    email = user_data.email.lower()
    _check_locked(email)
    user = await UserDB.get_by_email(email)

    if not user or not verify_password(user_data.password, user.get("hashed_password", "")):
        _register_fail(email)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    _login_fails.pop(email, None)

    if not user["is_active"]:
        # Cuenta sin verificar: enviar código nuevo (salvo que haya uno reciente o se llegó al límite)
        _issue_code(email, email, "verify", background_tasks)
        return PendingVerification(
            status="pending",
            message="Tu cuenta no está verificada. Revisa tu correo e ingresa el código que te enviamos.",
        )

    access_token = create_access_token(
        data={"sub": user["id"], "sv": user.get("session_version", 0)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=access_token, user_id=user["id"])


# ── Recuperar contraseña ──────────────────────────────────────────────────────
# Los códigos de reseteo se guardan con prefijo "reset:" para no mezclarse con
# los de verificación de cuenta.

_RESET_MSG = "Si existe una cuenta con ese correo, te enviamos un código para restablecer tu contraseña."


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(data: ForgotPasswordRequest, request: Request, background_tasks: BackgroundTasks):
    """Envía un código de 6 dígitos para restablecer la contraseña.
    Responde siempre lo mismo para no revelar qué correos están registrados
    (los límites por destinatario se aplican en silencio por la misma razón)."""
    _limit_ip_for_email(request)
    email = data.email.lower()
    user = await UserDB.get_by_email(email)
    if user:
        _issue_code(f"reset:{email}", email, "reset", background_tasks)
    return MessageResponse(message=_RESET_MSG)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(data: ResetPasswordRequest, request: Request):
    """Cambia la contraseña si el código enviado al correo es válido."""
    _limit_ip_for_auth(request)
    email = data.email.lower()
    if not verify_code(f"reset:{email}", data.code):
        raise HTTPException(status_code=400, detail="Código inválido o expirado")

    if not await UserDB.update_password(email, data.new_password):
        raise HTTPException(status_code=400, detail="Código inválido o expirado")
    usuario = await UserDB.get_by_email(email)
    if usuario:   # restablecer la contraseña también desconecta WhatsApp (INV-016, CHG-014)
        from app.api.routes.users import _desconectar_whatsapp
        await _desconectar_whatsapp(usuario["id"])

    _login_fails.pop(email, None)  # desbloquear el login tras el cambio
    return MessageResponse(message="Tu contraseña fue actualizada. Ya puedes iniciar sesión.")
