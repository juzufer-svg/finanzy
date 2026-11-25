"""
Validación de la entrada de la exportación de transacciones (CT-011, INV-044).

Los mensajes de error son los de CT-011. No hay parámetro de usuario: el dueño sale siempre de la sesión (INV-042).
"""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.plataapp import MES_PATTERN

MAX_MESES = 12
ANIO_MIN, ANIO_MAX = 2000, 2100   # igual que frontend/lib/exportar.ts
FORMATOS = ("csv", "xlsx")

MSG_MES_INVALIDO = "Formato de mes inválido (YYYY-MM)"
MSG_ORDEN = "El mes inicial no puede ser posterior al final"
MSG_DEMASIADOS_MESES = "Puedes exportar hasta 12 meses por archivo"
MSG_FORMATO = "Formato no válido: usa csv o xlsx"


class ParametrosInvalidos(ValueError):
    """La consulta no cumple CT-011 (el mensaje es el `detail` del 422)."""


class ConsultaExportacion(BaseModel):
    desde: str                      # YYYY-MM
    hasta: str                      # YYYY-MM (por defecto = desde)
    formato: Literal["csv", "xlsx"]

    @property
    def meses(self) -> int:
        return (int(self.hasta[:4]) - int(self.desde[:4])) * 12 + int(self.hasta[5:7]) - int(self.desde[5:7]) + 1

    @property
    def nombre_archivo(self) -> str:
        """Nombre genérico: sin nombre, correo ni ids (INV-042). Solo ASCII."""
        periodo = self.desde if self.desde == self.hasta else f"{self.desde}_a_{self.hasta}"
        return f"finanzy-transacciones-{periodo}.{self.formato}"


def _mes_valido(mes: Optional[str]) -> bool:
    """YYYY-MM con año entre 2000 y 2100; el rango de fechas se calcula aquí para que nada inválido llegue a la BD."""
    if mes is None or not MES_PATTERN.fullmatch(mes) or not ANIO_MIN <= int(mes[:4]) <= ANIO_MAX:
        return False
    try:
        date(int(mes[:4]), int(mes[5:7]), 1)
    except ValueError:
        return False
    return True


def validar_consulta(desde: Optional[str], hasta: Optional[str], formato: Optional[str]) -> ConsultaExportacion:
    """Valida mes inicial, mes final, orden, máximo de 12 meses y formato. Lanza `ParametrosInvalidos`."""
    if not _mes_valido(desde):
        raise ParametrosInvalidos(MSG_MES_INVALIDO)
    if hasta is None:
        hasta = desde
    elif not _mes_valido(hasta):
        raise ParametrosInvalidos(MSG_MES_INVALIDO)
    formato = "csv" if formato is None else formato
    if formato not in FORMATOS:
        raise ParametrosInvalidos(MSG_FORMATO)
    if desde > hasta:  # YYYY-MM se ordena igual como texto
        raise ParametrosInvalidos(MSG_ORDEN)
    consulta = ConsultaExportacion(desde=desde, hasta=hasta, formato=formato)
    if consulta.meses > MAX_MESES:
        raise ParametrosInvalidos(MSG_DEMASIADOS_MESES)
    return consulta
