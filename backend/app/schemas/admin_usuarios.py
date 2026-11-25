"""
Validación de la entrada del panel de administración de usuarios (CHG-023, CT-013, INV-058, INV-060).

Solo se valida DESPUÉS de confirmar al Dueño (INV-053). Los mensajes son los de CT-013 y NUNCA repiten lo recibido:
la contraseña del Dueño llega en el cuerpo del DELETE y no puede aparecer en ningún error.
"""
import json
import re
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

POR_PAGINA = 25
PAGINA_MAX = 400
Q_MAX = 60
CUERPO_MAX_BYTES = 2048

MSG_PAGINA = "La página debe ser un número entero entre 1 y 400"
MSG_Q = "La búsqueda debe tener entre 1 y 60 caracteres sin caracteres de control"
MSG_ID = "El identificador del usuario no es válido"
MSG_CUERPO = "Se esperan solo los campos confirmar_correo (3 a 255 caracteres) y contrasena_dueno (1 a 128 caracteres)"

_PAGINA = re.compile(r"[1-9][0-9]{0,2}")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class ParametrosInvalidos(ValueError):
    """La entrada no cumple CT-013 (el mensaje es el `detail` del 422; nunca incluye lo recibido)."""


def validar_pagina(valores: list[str]) -> int:
    """`pagina` ausente = 1; repetida, no entera o fuera de 1 a 400 → error."""
    if not valores:
        return 1
    if len(valores) != 1 or not _PAGINA.fullmatch(valores[0]) or int(valores[0]) > PAGINA_MAX:
        raise ParametrosInvalidos(MSG_PAGINA)
    return int(valores[0])


def _tiene_control(texto: str) -> bool:
    return any(ord(c) < 32 or 0x7F <= ord(c) <= 0x9F or c in "  " for c in texto)


def validar_q(valores: list[str]) -> Optional[str]:
    """`q` recortada, 1 a 60 caracteres sin control. Ausente o vacía = sin filtro (None). Repetida → error."""
    if not valores:
        return None
    if len(valores) != 1:
        raise ParametrosInvalidos(MSG_Q)
    q = valores[0].strip()
    if not q:
        return None
    if len(q) > Q_MAX or _tiene_control(q):
        raise ParametrosInvalidos(MSG_Q)
    return q


def validar_id(valor: str) -> str:
    """UUID con guiones (36 caracteres); devuelve la forma canónica en minúsculas."""
    if not isinstance(valor, str) or not _UUID.fullmatch(valor):
        raise ParametrosInvalidos(MSG_ID)
    return valor.lower()


class EliminarUsuarioIn(BaseModel):
    """Cuerpo del DELETE: SOLO estos dos campos y de tipo texto (sin conversiones)."""
    model_config = ConfigDict(extra="forbid", strict=True)

    confirmar_correo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]
    contrasena_dueno: Annotated[str, StringConstraints(min_length=1, max_length=128)]


def validar_cuerpo_eliminar(crudo: bytes) -> EliminarUsuarioIn:
    """Valida el cuerpo ya leído (con tope de 2 KB). Ausente, no JSON, clave extra o tipo distinto → error."""
    try:
        datos = json.loads(crudo.decode("utf-8")) if crudo else None
        if not isinstance(datos, dict):
            raise ParametrosInvalidos(MSG_CUERPO)
        return EliminarUsuarioIn.model_validate(datos)
    except (ValueError, ValidationError, RecursionError):   # el mensaje de pydantic repetiría la contraseña: se descarta
        raise ParametrosInvalidos(MSG_CUERPO) from None
