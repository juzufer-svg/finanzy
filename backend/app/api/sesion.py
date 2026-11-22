"""
Validación de la sesión (token Bearer) para las rutas protegidas.

Además de la firma y la expiración del JWT (INV-011), comprueba que la versión de
sesión del token (`sv`) coincida con la del usuario en la base de datos. Al
restablecer la contraseña la versión sube y todos los tokens anteriores dejan de
servir (INV-016).
"""
from typing import Optional

from fastapi import HTTPException

from app.core.security import decode_token
from app.models.user import UserDB

SESION_INVALIDA = "Tu sesión ya no es válida. Inicia sesión de nuevo."
_SERVICIO_NO_DISPONIBLE = "Servicio no disponible. Intenta de nuevo en unos minutos."


def _token_invalido() -> HTTPException:
    return HTTPException(status_code=401, detail="Token inválido")


async def usuario_de_sesion(authorization: Optional[str]) -> str:
    """Devuelve el id del usuario del token o lanza 401 (503 si la BD falla)."""
    try:
        scheme, token = authorization.split(" ", 1)
    except (ValueError, AttributeError):
        raise _token_invalido()
    if scheme.lower() != "bearer":
        raise _token_invalido()
    payload = decode_token(token.strip())
    if not payload or not payload.get("sub"):
        raise _token_invalido()
    user_id = str(payload["sub"])

    try:
        version_actual = await UserDB.get_session_version(user_id)
    except Exception as e:
        # Un fallo de Supabase no debe cerrar la sesión del usuario (el frontend
        # cierra la sesión ante un 401): se responde 503 y puede reintentar.
        print(f"[sesion] No se pudo verificar la versión de sesión ({type(e).__name__})")
        raise HTTPException(status_code=503, detail=_SERVICIO_NO_DISPONIBLE)

    # Los tokens emitidos antes de este cambio no traen "sv": cuentan como versión 0,
    # así nadie pierde la sesión al desplegar (la columna nace con 0).
    version_token = payload.get("sv", 0)
    if version_actual is None or type(version_token) is not int or version_token != version_actual:
        raise HTTPException(status_code=401, detail=SESION_INVALIDA)
    return user_id
