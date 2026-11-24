"""
Contadores diarios del Monitor (CHG-017, INV-036, CT-010).

Solo agregados por día de Colombia (UTC−5) (fecha, métrica, origen, cantidad): jamás correos, teléfonos, textos ni ids
de usuario. Con Supabase usa la tabla y las funciones de `backend/sql/2026-11-24_monitor.sql` (incremento
atómico por RPC); sin Supabase (desarrollo y pruebas) guarda en memoria. En producción NUNCA se guarda en
memoria (INV-013): sin Supabase simplemente no se cuenta.

Un fallo al contar jamás interrumpe el flujo principal: `incrementar` captura todo error y deja un aviso
sin datos sensibles (solo el nombre de la métrica y el tipo de error).
"""
import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.core.supabase import SupabaseDB

METRICAS = (
    "claude_llamadas", "claude_tokens_entrada", "claude_tokens_salida",
    "brevo_correos_enviados", "whatsapp_enviados", "whatsapp_recibidos",
)
METRICA_PURGA = "purga"          # fila marcadora de «última purga»; no es consumo y nunca se expone
ORIGENES = ("asistente", "whatsapp", "general")
ORIGENES_CLAUDE = ("asistente", "whatsapp")
VENTANA_DIAS = 30                # ventana de lectura (incluido hoy)
RETENCION_DIAS = 90              # la purga borra fecha < hoy - 90


def _supabase_ok() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_KEY)


# EXCEPCIÓN DELIBERADA a «fechas en UTC» de CLAUDE.md (aprobada por el dueño, CHG-017, ADR-008): los DÍAS de los
# contadores propios cortan a medianoche de Colombia. Colombia es UTC−5 todo el año (sin horario de verano), así
# que basta una zona fija, sin depender de tzdata. Los instantes (`generado_en`, `actualizado_en`) siguen en UTC.
COLOMBIA = timezone(timedelta(hours=-5))


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def hoy_colombia(ahora: Optional[datetime] = None) -> date:
    """Día calendario de Colombia (UTC−5) del instante `ahora` (con zona; por defecto, el reloj actual).
    Única fuente de «hoy», «mes en curso», ventana de 30 días, `desde` y purga a 90 días de los contadores."""
    return (ahora or _ahora_utc()).astimezone(COLOMBIA).date()


class _Memoria:
    """Almacén del modo demo (se vacía en las pruebas): (fecha, métrica, origen) → cantidad."""
    filas: dict[tuple[date, str, str], int] = {}
    # Día del último intento de purga en Supabase hecho por ESTA instancia (la marca en la tabla sigue
    # garantizando una sola purga por día entre instancias)
    ultima_purga: Optional[date] = None

    @classmethod
    def limpiar(cls) -> None:
        cls.filas.clear()
        cls.ultima_purga = None


def _incrementar_o_falla(metrica: str, origen: str, cantidad: int) -> None:
    hoy = hoy_colombia()
    if _supabase_ok():
        client = SupabaseDB.get_client()
        client.rpc("incrementar_contador", {
            "p_fecha": hoy.isoformat(), "p_metrica": metrica, "p_origen": origen, "p_cantidad": cantidad,
        }).execute()
        _purgar_si_toca(client, hoy)
        return
    if settings.es_produccion:
        raise RuntimeError("sin Supabase en producción")   # INV-013: no se guarda en memoria
    clave = (hoy, metrica, origen)
    _Memoria.filas[clave] = _Memoria.filas.get(clave, 0) + cantidad
    _purgar_memoria(hoy)


def _purgar_si_toca(client, hoy: date) -> None:
    """Purga oportunista: la función SQL solo purga si logra insertar la marca del día (una por día, aun con
    varias instancias). Un fallo aquí no cuenta como fallo del contador."""
    if _Memoria.ultima_purga == hoy:
        return   # esta instancia ya lo intentó hoy: ahorra una llamada a la red por cada incremento
    _Memoria.ultima_purga = hoy
    try:
        client.rpc("purgar_contadores", {"p_hoy": hoy.isoformat()}).execute()
    except Exception as e:
        print(f"[contadores] Aviso: no se pudo purgar ({type(e).__name__})")


def _purgar_memoria(hoy: date) -> None:
    marca = (hoy, METRICA_PURGA, "general")
    if marca in _Memoria.filas:
        return
    _Memoria.filas[marca] = 0
    limite = hoy - timedelta(days=RETENCION_DIAS)
    for clave in [c for c in _Memoria.filas if c[0] < limite]:
        del _Memoria.filas[clave]


def incrementar(metrica: str, origen: str = "general", cantidad: int = 1) -> bool:
    """Suma `cantidad` al contador de hoy. Devuelve True si se contó. NUNCA lanza (INV-036)."""
    try:
        if metrica not in METRICAS or origen not in ORIGENES:
            print("[contadores] Aviso: métrica u origen fuera de la lista fija; no se cuenta")
            return False
        if type(cantidad) is not int or cantidad < 0:
            print(f"[contadores] Aviso: cantidad inválida para {metrica}; no se cuenta")
            return False
        if cantidad == 0:
            return False
        _incrementar_o_falla(metrica, origen, cantidad)
        return True
    except Exception as e:
        # Solo la métrica y el tipo del error: nunca datos del usuario ni el mensaje del servidor
        print(f"[contadores] Aviso: no se pudo contar {metrica} ({type(e).__name__})")
        return False


async def incrementar_async(metrica: str, origen: str = "general", cantidad: int = 1) -> bool:
    """Igual que `incrementar` (NUNCA lanza), pero sin bloquear el event loop cuando hay que hablar con
    Supabase: la llamada de red va a un hilo. Sin Supabase (memoria) no hay red y se ejecuta directo."""
    if not _supabase_ok():
        return incrementar(metrica, origen, cantidad)
    try:
        return await asyncio.to_thread(incrementar, metrica, origen, cantidad)
    except Exception as e:   # to_thread no debería fallar; CancelledError sí se propaga
        print(f"[contadores] Aviso: no se pudo contar {metrica} ({type(e).__name__})")
        return False


def leer_ventana() -> list[dict]:
    """Filas de los últimos 30 días de Colombia (incluido hoy) sin la marca de purga: [{fecha, metrica, origen, cantidad}].

    A diferencia de `incrementar`, los errores se propagan: quien lee (T2) decide qué responder."""
    desde = hoy_colombia() - timedelta(days=VENTANA_DIAS - 1)
    if _supabase_ok():
        client = SupabaseDB.get_client()
        r = (client.table("contadores_diarios").select("fecha,metrica,origen,cantidad")
             .gte("fecha", desde.isoformat()).neq("metrica", METRICA_PURGA).order("fecha").execute())
        return [{"fecha": str(f["fecha"]), "metrica": f["metrica"], "origen": f["origen"],
                 "cantidad": int(f["cantidad"])} for f in (r.data or [])]
    return [{"fecha": f.isoformat(), "metrica": m, "origen": o, "cantidad": c}
            for (f, m, o), c in sorted(_Memoria.filas.items())
            if f >= desde and m != METRICA_PURGA]


METRICAS_CLAUDE = ("claude_llamadas", "claude_tokens_entrada", "claude_tokens_salida")


def leer_mes_claude(origen: str = "asistente") -> dict[str, int]:
    """Totales del MES de Colombia en curso (del día 1 a hoy) de las métricas de Claude de UN origen (por defecto
    `asistente`; el origen `whatsapp` nunca se mezcla): {metrica: total}, con 0 donde no hay filas.

    Los errores se propagan: quien lee decide qué responder (el Monitor lo marca «no disponible»)."""
    if origen not in ORIGENES_CLAUDE:
        raise ValueError("origen fuera de la lista fija")
    desde = hoy_colombia().replace(day=1)
    totales = {m: 0 for m in METRICAS_CLAUDE}
    if _supabase_ok():
        client = SupabaseDB.get_client()
        r = (client.table("contadores_diarios").select("metrica,cantidad")
             .gte("fecha", desde.isoformat()).eq("origen", origen).in_("metrica", list(METRICAS_CLAUDE)).execute())
        filas = [(f["metrica"], int(f["cantidad"])) for f in (r.data or [])]
    else:
        filas = [(m, c) for (f, m, o), c in _Memoria.filas.items() if f >= desde and o == origen]
    for metrica, cantidad in filas:
        if metrica in totales:
            totales[metrica] += cantidad
    return totales


def fecha_mas_antigua() -> Optional[str]:
    """Fecha (YYYY-MM-DD) del contador más antiguo conservado, sin contar la marca de purga; None si no hay."""
    if _supabase_ok():
        client = SupabaseDB.get_client()
        r = (client.table("contadores_diarios").select("fecha").neq("metrica", METRICA_PURGA)
             .order("fecha").limit(1).execute())
        return str(r.data[0]["fecha"]) if r.data else None
    fechas = [f for (f, m, _o) in _Memoria.filas if m != METRICA_PURGA]
    return min(fechas).isoformat() if fechas else None
