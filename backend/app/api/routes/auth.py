"""
Authentication routes

Estado persistente (CHG-020, ADR-010): bloqueos de login, códigos y límites viven en PostgreSQL (`models/auth_estado.py`).
Fail-closed (INV-039): si la BD de estado o la lectura de usuarios falla, 503; nunca se deja pasar.
"""
from datetime import timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from app.schemas.auth import (
    UserRegistration, UserLogin, Token,
    VerifyEmailRequest, ResendCodeRequest, PendingVerification,
    ForgotPasswordRequest, ResetPasswordRequest, MessageResponse,
)
from app.models import auth_estado
from app.models.auth_estado import EstadoNoDisponible
from app.models.user import UserDB
from app.models.whatsapp import WhatsappDB
from app.core.security import (
    create_access_token, verify_password, verify_password_senuelo, codigo_senuelo,
)
from app.core.config import settings
from app.core.rate_limit import enforce_persistente, ip_intentos_auth, ip_pedidos_codigo
from app.utils.email import generate_code, send_verification_email

_TOO_MANY = "Demasiadas solicitudes. Espera unos minutos e intenta de nuevo."
_LIMITED_MSG = "Ya enviamos varios códigos a este correo hoy. Revisa tu bandeja (y spam) o intenta mañana."
_BLOQUEADO_MSG = "Demasiados intentos fallidos. Intenta de nuevo en 15 minutos."
_SUSPENDIDA_MSG = "No fue posible iniciar sesión con esta cuenta. Contacta al administrador."   # CHG-023, INV-056
PRESUPUESTO_REINICIO_SEG = 4.0


async def iniciar_presupuesto_peticion() -> None:
    """Dependencia de todas las rutas de autenticación: fija el presupuesto de 5 s de la petición (INV-039).
    Es asíncrona para que la variable de contexto llegue a la ruta (las síncronas corren en otro hilo)."""
    auth_estado.iniciar_presupuesto()


router = APIRouter(dependencies=[Depends(iniciar_presupuesto_peticion)])


async def leer_usuario(email: str):
    """Lectura ESTRICTA del usuario (INV-039): un fallo de la tabla de usuarios es 503, nunca «no existe»."""
    try:
        return await UserDB.get_by_email_estricto(email)
    except EstadoNoDisponible:
        raise
    except Exception as e:   # el mensaje del servidor puede traer datos personales: solo el tipo
        print(f"[auth] Aviso: falló la lectura de usuarios ({type(e).__name__})")
        raise EstadoNoDisponible("falló la lectura de usuarios")


async def limitar_ip_para_correo(request: Request) -> None:
    await enforce_persistente(ip_pedidos_codigo, request, _TOO_MANY)


async def limitar_ip_para_auth(request: Request) -> None:
    await enforce_persistente(ip_intentos_auth, request, _TOO_MANY)


async def reservar_intento_de_login(email: str) -> None:
    """Cuenta el intento ANTES de comprobar la contraseña (INV-038). 429 si el correo está bloqueado."""
    permitido, _hasta = await auth_estado.login_reservar(email)
    if not permitido:
        raise HTTPException(status_code=429, detail=_BLOQUEADO_MSG)


async def reiniciar_login_sin_fallar(email: str, origen: str) -> None:
    """Desbloquea el login DESPUÉS de haber cambiado la contraseña (best-effort, I-2): si la BD de estado falla, el
    cambio ya está hecho y gastado el código, así que NO se responde 503 (INV-027); solo un aviso sin datos. El bloqueo
    vence solo a los 15 min como mucho. Usa un presupuesto PROPIO y fresco de 4 s (M-B): lo que ya gastó la petición (BD de
    usuarios, bcrypt) no debe dejarlo sin tiempo para desbloquear."""
    auth_estado.iniciar_presupuesto(PRESUPUESTO_REINICIO_SEG)
    try:
        await auth_estado.login_reiniciar(email)
    except EstadoNoDisponible:
        print(f"[{origen}] Aviso: no se pudo reiniciar el bloqueo de login tras cambiar la contraseña")


async def comprobar_contrasena(contrasena: str, hashed: str) -> bool:
    """bcrypt (~0,3 s) FUERA del event loop (I-6) y en el ejecutor PROPIO y acotado de bcrypt (M-A): con 8 comprobaciones
    en curso la siguiente recibe 503 sin encolarse (`EstadoNoDisponible`)."""
    return await auth_estado.ejecutar_bcrypt("verificar_contrasena", lambda: verify_password(contrasena, hashed))


async def comprobar_contrasena_senuelo(contrasena: str) -> bool:
    """Mismo costo bcrypt y mismo hilo que una comprobación real (INV-009, M-5), también fuera del event loop."""
    return await auth_estado.ejecutar_bcrypt("verificar_contrasena", lambda: verify_password_senuelo(contrasena))


async def cerrar_reserva_tras_fallo_interno(email: str) -> None:
    """Si algo falla entre reservar y resolver, se cierra la reserva como fallo (el intento ya estaba contado)."""
    try:
        await auth_estado.login_resolver(email, False)
    except EstadoNoDisponible:
        pass


async def _issue_code(
    email: str, purpose: str, background_tasks: BackgroundTasks, *, enviar: bool = True
) -> str:
    """Emite un código con una SOLA operación atómica de la BD (60 s, topes y guardado, INV-038).

    Con `enviar=False` ejecuta y cuenta IGUAL pero guarda un código señuelo (que nunca puede verificarse) y no envía
    nada: así «no existe» y «existe» son indistinguibles (INV-009).

    Devuelve:
      "sent"     → se emitió un código nuevo
      "recent"   → ya se emitió uno hace menos de 60 s (sigue válido)
      "limited"  → se alcanzó el límite diario (por destinatario o global)
    """
    codigo = generate_code() if enviar else codigo_senuelo()
    resultado = await auth_estado.codigo_emitir(email, purpose, codigo)
    if resultado == "enviado":
        if enviar:
            background_tasks.add_task(send_verification_email, email, codigo, purpose)
        # La purga NO corre aquí (I-4, I-A): la dispara el middleware PurgaEnSegundoPlano, tras responder
        return "sent"
    return "recent" if resultado == "reciente" else "limited"


# ── Register ──────────────────────────────────────────────────────────────────

@router.post("/register", response_model=PendingVerification, status_code=201)
async def register(user_data: UserRegistration, request: Request, background_tasks: BackgroundTasks):
    """Register a new user and send verification code to email"""
    await limitar_ip_para_correo(request)
    email = user_data.email.lower()

    existing = await leer_usuario(email)
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

    if await _issue_code(email, "verify", background_tasks) == "limited":
        raise HTTPException(status_code=429, detail=_LIMITED_MSG)

    return PendingVerification(
        status="pending",
        message="Te enviamos un código de 6 dígitos a tu correo. Ingrésalo para activar tu cuenta.",
    )


# ── Verify email ──────────────────────────────────────────────────────────────

@router.post("/verify-email", response_model=Token)
async def verify_email(data: VerifyEmailRequest, request: Request, background_tasks: BackgroundTasks):
    """Verify email code and return JWT"""
    await limitar_ip_para_auth(request)
    email = data.email.lower()

    # El usuario se lee ANTES de consumir el código: si la lectura falla (503) el código no se gasta (INV-039).
    user = await leer_usuario(email)

    if await auth_estado.codigo_verificar(email, "verify", data.code) != "ok":
        raise HTTPException(status_code=400, detail="Código inválido o expirado")

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.get("suspendida"):   # una cuenta suspendida no recibe sesión (INV-056)
        raise HTTPException(status_code=403, detail=_SUSPENDIDA_MSG)

    await UserDB.activate(email)
    background_tasks.add_task(UserDB.registrar_acceso, user["id"])   # tras responder, mejor esfuerzo (INV-061)

    access_token = create_access_token(
        data={"sub": user["id"], "sv": user.get("session_version", 0)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=access_token, user_id=user["id"], full_name=user.get("full_name"))


# ── Resend code ───────────────────────────────────────────────────────────────

@router.post("/resend-code", response_model=PendingVerification)
async def resend_code(data: ResendCodeRequest, request: Request, background_tasks: BackgroundTasks):
    """Reenvía el código de verificación de una cuenta pendiente.
    Responde y cuenta IGUAL exista o no la cuenta (y esté pendiente o activa): una sola emisión con los mismos
    60 s y topes y el mismo 429; solo una cuenta pendiente recibe el correo (INV-009)."""
    await limitar_ip_para_correo(request)
    email = data.email.lower()
    user = await leer_usuario(email)

    pendiente = bool(user) and not user["is_active"]
    if await _issue_code(email, "verify", background_tasks, enviar=pendiente) == "limited":
        raise HTTPException(status_code=429, detail=_LIMITED_MSG)

    return PendingVerification(
        status="pending",
        message="Si tu cuenta está pendiente de verificación, te enviamos un código a tu correo.",
    )


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(user_data: UserLogin, request: Request, background_tasks: BackgroundTasks):
    """Login with email + password. Returns JWT or pending verification."""
    await limitar_ip_para_auth(request)
    email = user_data.email.lower()
    await reservar_intento_de_login(email)   # el intento se cuenta ANTES de comprobar la contraseña (INV-038)

    try:
        user = await leer_usuario(email)
    except EstadoNoDisponible:
        await cerrar_reserva_tras_fallo_interno(email)
        raise

    try:
        if user:
            acierto = await comprobar_contrasena(user_data.password, user.get("hashed_password", ""))
        else:
            await comprobar_contrasena_senuelo(user_data.password)   # mismo costo bcrypt que con una cuenta real (INV-009, M-5)
            acierto = False
    except EstadoNoDisponible:   # bcrypt lleno o sin presupuesto (M-A): 503 y la reserva se cierra como fallo (ya estaba contada)
        await cerrar_reserva_tras_fallo_interno(email)
        raise

    await auth_estado.login_resolver(email, acierto)
    if not acierto:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    if user.get("suspendida"):
        # Solo con la contraseña CORRECTA (un 401 con la incorrecta no revela el estado, INV-056/INV-009): sin token ni
        # código; no cuenta como fallo (la reserva ya se resolvió como acierto)
        raise HTTPException(status_code=403, detail=_SUSPENDIDA_MSG)

    if not user["is_active"]:
        # Cuenta sin verificar: enviar código nuevo (salvo que haya uno reciente o se llegó al límite)
        await _issue_code(email, "verify", background_tasks)
        return PendingVerification(
            status="pending",
            message="Tu cuenta no está verificada. Revisa tu correo e ingresa el código que te enviamos.",
        )

    background_tasks.add_task(UserDB.registrar_acceso, user["id"])   # tras responder, mejor esfuerzo (INV-061)
    access_token = create_access_token(
        data={"sub": user["id"], "sv": user.get("session_version", 0)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=access_token, user_id=user["id"])


# ── Recuperar contraseña ──────────────────────────────────────────────────────
# Los códigos de reseteo tienen su propio propósito ("reset") para no mezclarse con los de verificación.

_RESET_MSG = "Si existe una cuenta con ese correo, te enviamos un código para restablecer tu contraseña."


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(data: ForgotPasswordRequest, request: Request, background_tasks: BackgroundTasks):
    """Envía un código de 6 dígitos para restablecer la contraseña.
    Responde siempre lo mismo para no revelar qué correos están registrados: ejecuta y cuenta IGUAL exista o no la
    cuenta (código señuelo sin envío) y los topes por destinatario se aplican en silencio (200)."""
    await limitar_ip_para_correo(request)
    email = data.email.lower()
    user = await leer_usuario(email)
    await _issue_code(email, "reset", background_tasks, enviar=bool(user))
    return MessageResponse(message=_RESET_MSG)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(data: ResetPasswordRequest, request: Request):
    """Cambia la contraseña si el código enviado al correo es válido."""
    await limitar_ip_para_auth(request)
    email = data.email.lower()

    # El usuario se lee ANTES de consumir el código: si la lectura falla (503) el código no se gasta (INV-039).
    usuario = await leer_usuario(email)

    if await auth_estado.codigo_verificar(email, "reset", data.code) != "ok" or not usuario:
        raise HTTPException(status_code=400, detail="Código inválido o expirado")

    # Restablecer la contraseña también desconecta WhatsApp (INV-016, CHG-014). Se hace ANTES de cambiarla:
    # si la BD falla, no se cambia nada (nunca queda la contraseña nueva con el WhatsApp viejo conectado).
    try:
        await WhatsappDB.desenlazar(usuario["id"])
    except Exception as e:
        print(f"[auth.reset_password] No se pudo desconectar WhatsApp ({type(e).__name__})")
        raise HTTPException(status_code=503, detail=auth_estado.MENSAJE_503)

    if not await UserDB.update_password(email, data.new_password):
        raise HTTPException(status_code=400, detail="Código inválido o expirado")

    # Desbloquear el login tras el cambio (también si otra persona lo bloqueó). Best-effort: la contraseña ya cambió y el
    # código ya se gastó, así que un fallo de la BD de estado no puede convertirse en 503 (I-2, INV-027)
    await reiniciar_login_sin_fallar(email, "auth.reset_password")
    return MessageResponse(message="Tu contraseña fue actualizada. Ya puedes iniciar sesión.")
