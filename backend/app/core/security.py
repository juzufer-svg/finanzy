"""
Security utilities - JWT (PyJWT) and password hashing (bcrypt)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

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
