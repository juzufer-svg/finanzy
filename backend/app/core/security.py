"""
Security utilities - JWT (PyJWT) and password hashing (bcrypt)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import secrets

import bcrypt
import jwt

from app.core.config import settings

# Solo se aceptan algoritmos HMAC: evita confusiones de algoritmo ("none",
# claves públicas usadas como secreto, etc.) aunque ALGORITHM venga mal configurado.
_ALLOWED_ALGORITHMS = {"HS256", "HS384", "HS512"}
_ALGORITHM = settings.ALGORITHM if settings.ALGORITHM in _ALLOWED_ALGORITHMS else "HS256"

# bcrypt solo usa los primeros 72 bytes de la contraseña. passlib los recortaba en
# silencio; se mantiene ese comportamiento para que los hashes existentes sigan
# validando (bcrypt >= 5 lanza error con entradas más largas).
_BCRYPT_MAX_BYTES = 72


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash (acepta hashes $2a$, $2b$ y $2y$)"""
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(_password_bytes(plain_password), hashed_password.encode("utf-8"))
    except ValueError:
        # hash con formato inválido
        return False


# Hash señuelo (CHG-020, INV-009, M-5): se calcula una vez al arrancar con el MISMO costo que los hashes reales
# (`get_password_hash`), para que el login con un correo inexistente ejecute la misma comprobación bcrypt y no se
# distinga por tiempo. La contraseña de origen es aleatoria y se descarta: nadie puede acertarla.
HASH_SENUELO = get_password_hash(secrets.token_urlsafe(32))


def verify_password_senuelo(plain_password: str) -> bool:
    """Comprueba bcrypt contra el hash señuelo (cuenta inexistente). Siempre False en la práctica; el resultado
    se ignora. Pasa por `verify_password` para que las pruebas cuenten las llamadas."""
    return verify_password(plain_password, HASH_SENUELO)


def codigo_senuelo() -> str:
    """Código señuelo para cuentas inexistentes o ya activas (INV-009, INV-039): 32 bytes aleatorios. Ningún código
    de 6 dígitos puede producir el mismo HMAC, así que nunca puede verificarse (si no, adivinar 6 dígitos sobre una
    cuenta activa daría una sesión). No se envía por correo."""
    return "senuelo:" + secrets.token_hex(32)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate JWT token (firma y expiración)"""
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        return None
