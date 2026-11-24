"""
Comprobación del «Dueño» (CHG-017, INV-031, ADR-008).

El Dueño es quien inicia sesión con el correo de `OWNER_EMAIL`. La comparación es la misma en el Monitor y en
`es_dueno` de `GET /users/me`: ambos correos con `strip().lower()` y `hmac.compare_digest` sobre sus bytes
(tiempo constante). Fail-closed: `OWNER_EMAIL` vacío o ausente, o cualquier problema, significa «no es el Dueño».
El correo del Dueño nunca está escrito en el código ni sale en ninguna respuesta.
"""
import hmac
from typing import Any

from app.core.config import settings


def _normalizar(correo: Any) -> str:
    return correo.strip().lower() if isinstance(correo, str) else ""


def es_correo_dueno(correo: Any) -> bool:
    """True solo si `correo` es el de OWNER_EMAIL. Nunca lanza."""
    try:
        dueno = _normalizar(settings.OWNER_EMAIL)
        candidato = _normalizar(correo)
        if not dueno or not candidato:   # dos vacíos NO son iguales: sin OWNER_EMAIL nadie es Dueño
            return False
        return hmac.compare_digest(candidato.encode("utf-8"), dueno.encode("utf-8"))
    except Exception:
        return False
