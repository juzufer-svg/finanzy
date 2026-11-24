"""
Users routes
"""
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Header, Request, status
from app.schemas.auth import (
    UserResponse, UpdateCurrencyRequest, UpdateProfileRequest, ChangePasswordRequest, Token,
)
from app.models.user import UserDB
from app.models.whatsapp import WhatsappDB
from app.api.sesion import usuario_de_sesion
from app.api.dueno import es_correo_dueno
from app.api.routes import auth as auth_routes
from app.core.config import settings
from app.core.security import create_access_token, verify_password

_NO_DISPONIBLE = "No se pudo guardar el cambio. Intenta de nuevo en unos minutos."


router = APIRouter()


def _respuesta_usuario(user: dict) -> UserResponse:
    """UserResponse con `es_dueno` calculado en el servidor (CHG-017, CT-002): nunca viene de la BD ni del
    cliente, es false ante cualquier fallo y jamás incluye el correo del dueño."""
    try:
        dueno = es_correo_dueno(user.get("email"))
    except Exception:
        dueno = False
    return UserResponse(**{**user, "es_dueno": dueno})


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(authorization: str = Header(...)):
    """Get current user information"""
    user_id = await usuario_de_sesion(authorization)
    user = await UserDB.get_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return _respuesta_usuario(user)


@router.put("/me/currency", response_model=UserResponse)
async def update_user_currency(request: UpdateCurrencyRequest, authorization: str = Header(...)):
    """Update user's currency preference"""
    user_id = await usuario_de_sesion(authorization)
    
    # Verify user exists
    user = await UserDB.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Si no se pudo guardar, se informa el error: nunca se simula un éxito (CHG-002)
    try:
        guardado = await UserDB.update_currency(user_id, request.currency)
    except Exception as e:
        print(f"[users.update_currency] {type(e).__name__}")
        guardado = False
    if not guardado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo guardar la moneda. Intenta de nuevo en unos minutos.",
        )

    # Fetch updated user
    updated_user = await UserDB.get_by_id(user_id)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return _respuesta_usuario(updated_user)


@router.put("/me", response_model=UserResponse)
async def update_profile(request: UpdateProfileRequest, authorization: str = Header(...)):
    """Cambia el nombre visible del usuario (CHG-012)."""
    user_id = await usuario_de_sesion(authorization)
    nombre = " ".join(request.full_name.split())  # sin espacios repetidos ni en los extremos
    if len(nombre) < 2:
        raise HTTPException(status_code=422, detail="El nombre debe tener al menos 2 caracteres")
    try:
        guardado = await UserDB.update_full_name(user_id, nombre)
    except Exception as e:
        print(f"[users.update_profile] {type(e).__name__}")
        guardado = False
    if not guardado:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_DISPONIBLE)
    user = await UserDB.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return _respuesta_usuario(user)


@router.post("/me/password", response_model=Token)
async def change_password(data: ChangePasswordRequest, request: Request, authorization: str = Header(...)):
    """Cambia la contraseña con la actual (CHG-012, INV-027).

    Sube la versión de sesión: se cierran las sesiones de los demás dispositivos (INV-016) y
    esta recibe un token nuevo (el proxy de Next.js lo guarda en la cookie y lo quita de la respuesta).
    Una contraseña actual incorrecta responde 400 (no 401: el frontend cierra la sesión ante un 401)
    y cuenta como intento fallido del login: 5 fallos bloquean el correo 15 minutos (INV-010).
    """
    user_id = await usuario_de_sesion(authorization)
    auth_routes._limit_ip_for_auth(request)
    user = await UserDB.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    email = user["email"].lower()
    auth_routes._check_locked(email)
    if not verify_password(data.actual, user.get("hashed_password", "")):
        auth_routes._register_fail(email)
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta")
    if data.nueva == data.actual:
        raise HTTPException(status_code=422, detail="La nueva contraseña debe ser distinta de la actual")

    # Cambiar la contraseña también desconecta WhatsApp (INV-016, CHG-014). Antes de cambiarla: si la BD
    # falla, no se cambia nada (nunca queda la contraseña nueva con el WhatsApp viejo conectado).
    try:
        await WhatsappDB.desenlazar(user_id)
    except Exception as e:
        print(f"[users.change_password] No se pudo desconectar WhatsApp ({type(e).__name__})")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_DISPONIBLE)

    try:
        nueva_version = await UserDB.update_password(email, data.nueva)
    except Exception as e:
        print(f"[users.change_password] {type(e).__name__}")
        nueva_version = 0
    # La versión nueva sale de la misma escritura: no se vuelve a leer la BD, así un fallo
    # posterior no puede dejar la contraseña cambiada con un error en pantalla (INV-027).
    if type(nueva_version) is not int or nueva_version < 1:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_DISPONIBLE)
    auth_routes._login_fails.pop(email, None)

    token = create_access_token(
        data={"sub": user_id, "sv": nueva_version},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=token, user_id=user_id, full_name=user.get("full_name") or None)


@router.delete("/me", status_code=204)
async def delete_current_user(authorization: str = Header(...)):
    """Delete the authenticated user's account permanently"""
    user_id = await usuario_de_sesion(authorization)
    deleted = await UserDB.delete_by_id(user_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
