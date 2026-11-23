"""
Cálculo de la próxima fecha de una transacción recurrente (CHG-012, INV-026).

Frecuencias:
- semanal: cada 7 días.
- mensual: el mismo día de cada mes (el "día ancla"); si el mes no lo tiene, el último día
  del mes (31 → 30 de abril → 31 de mayo: el ancla no se pierde tras un mes corto).
- quincenal: dos veces al mes, en el día ancla y 15 días después (o antes), ajustado al
  último día del mes. Ejemplos: ancla 15 → días 15 y 30 (28/29 en febrero); ancla 1 → 1 y 16;
  ancla 20 → 5 y 20.
"""
import calendar
from datetime import date, timedelta


def _ultimo_dia(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]


def _en_mes(anio: int, mes: int, dia: int) -> date:
    """El día pedido o, si el mes es más corto, su último día."""
    return date(anio, mes, min(dia, _ultimo_dia(anio, mes)))


def _mes_siguiente(anio: int, mes: int) -> tuple[int, int]:
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def siguiente_fecha(actual: date, frecuencia: str, dia_ancla: int) -> date:
    """Primera fecha de la serie estrictamente posterior a `actual`."""
    if frecuencia == "semanal":
        return actual + timedelta(days=7)
    if not 1 <= dia_ancla <= 31:
        raise ValueError("El día ancla debe estar entre 1 y 31")
    if frecuencia == "mensual":
        anio, mes = actual.year, actual.month
        candidata = _en_mes(anio, mes, dia_ancla)
        if candidata > actual:
            return candidata
        anio, mes = _mes_siguiente(anio, mes)
        return _en_mes(anio, mes, dia_ancla)
    if frecuencia == "quincenal":
        primero = dia_ancla if dia_ancla <= 15 else dia_ancla - 15
        dias = (primero, primero + 15)
        anio, mes = actual.year, actual.month
        for _ in range(2):  # este mes y el siguiente bastan: siempre hay una fecha en el mes que sigue
            for dia in dias:
                candidata = _en_mes(anio, mes, dia)
                if candidata > actual:
                    return candidata
            anio, mes = _mes_siguiente(anio, mes)
    raise ValueError(f"Frecuencia no permitida: {frecuencia}")
