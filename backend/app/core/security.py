"""Utilidades de seguridad para hash de contraseñas y validación JWT."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
JWT_ALGORITHM = "HS256"

def get_password_hash(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("La contraseña no puede estar vacía")
    # bcrypt procesa como máximo 72 bytes; evitar truncamientos silenciosos.
    if len(password.encode("utf-8")) > 72:
        raise ValueError("La contraseña supera el límite seguro de 72 bytes para bcrypt")
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not isinstance(plain_password, str) or not isinstance(hashed_password, str):
        return False
    if not hashed_password or len(plain_password.encode("utf-8")) > 72:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    if not isinstance(data, dict) or not data.get("sub"):
        raise ValueError("El JWT requiere un subject")
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {**data, "iat": int(now.timestamp()), "exp": int(expire.timestamp())}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    if not isinstance(token, str) or not token or len(token) > 8192:
        return None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM],
            options={"require_exp": True, "require_sub": True},
        )
        if not isinstance(payload.get("sub"), str) or not payload["sub"]:
            return None
        return payload
    except (JWTError, ValueError, TypeError):
        return None
