"""
Rango de fechas permitido en transacciones y transferencias (CHG-027, INV-063).

Una fecha solo es válida si `2026-01-01 <= fecha <= hoy + 365 días`, donde «hoy» es el día de Colombia
(UTC−5, `contadores.hoy_colombia()`, la misma fuente que el resto de la app). Función única: la usan los
esquemas Pydantic, la edición de transacciones, la confirmación de recurrentes y WhatsApp.
"""
from datetime import date, timedelta
from typing import Optional

from app.models.contadores import hoy_colombia

FECHA_MINIMA = date(2026, 1, 1)
DIAS_ADELANTE = 365
MSG_FECHA_FUERA_DE_RANGO_WHATSAPP = "La fecha está fuera del rango permitido"


def fecha_maxima() -> date:
    """Última fecha admitida hoy: día de Colombia + 365 días."""
    return hoy_colombia() + timedelta(days=DIAS_ADELANTE)


def mensaje_fuera_de_rango() -> str:
    return f"La fecha debe estar entre el 1 de enero de 2026 y el {fecha_maxima().strftime('%d/%m/%Y')}"


def fecha_en_rango(valor) -> bool:
    """¿La fecha (`date` o texto YYYY-MM-DD, con o sin hora) está dentro del rango? Un texto que no es fecha devuelve True:
    ese formato lo rechazan los demás validadores, como antes (esta regla solo juzga el rango)."""
    d = _a_fecha(valor)
    return d is None or FECHA_MINIMA <= d <= fecha_maxima()


def validar_rango_fecha(valor):
    """Devuelve `valor` si está en rango; si no, `ValueError` con el mensaje fijo (Pydantic lo convierte en 422)."""
    if not fecha_en_rango(valor):
        raise ValueError(mensaje_fuera_de_rango())
    return valor


def _a_fecha(valor) -> Optional[date]:
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None
