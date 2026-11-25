"""
Ejecutor PROPIO y acotado de las transacciones (CHG-026, BL-043, ADR-009 punto 14). Mismo patrón que `models/cuentas.py`.

Las llamadas a Supabase de `TransaccionDB` corren aquí (4 hilos llamados `transacciones`, `_huecos`), SEPARADO de los 8 hilos de
`auth-estado` (login) y de los 4 de `cuentas`: con la BD lenta, las transacciones no pueden dejar sin hilos a esos flujos. Usa el
cliente dedicado de `auth_estado` (plazo de 4 s, sin reintentos), el presupuesto de 5 s por petición y responde 503 inmediato,
sin encolar, si no hay hueco. Cualquier fallo o respuesta inesperada = `EstadoNoDisponible` (503 genérico, sin texto de la BD).
Solo los errores de la regla de cuentas (SQLSTATE en `cuentas.CODIGOS_NEGOCIO`: FZ001/FZ002 → 409, 22003 → 422, …) vuelven como
`ErrorBD`, que las rutas traducen con `cuentas_errores`.
Privacidad: ningún aviso lleva el texto de la excepción (solo el nombre de la operación y el tipo).
"""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from app.models import auth_estado
from app.models.auth_estado import EstadoNoDisponible
from app.models.cuentas import CODIGOS_NEGOCIO
from app.models.demo_db import ErrorBD

MAX_HILOS_TRANSACCIONES = 4
_huecos = threading.BoundedSemaphore(MAX_HILOS_TRANSACCIONES)   # uno por hilo; se libera al terminar el HILO (aunque venza el plazo)
_ejecutor = ThreadPoolExecutor(max_workers=MAX_HILOS_TRANSACCIONES, thread_name_prefix="transacciones")


async def llamar(operacion: str, fn):
    """Corre `fn` (bloqueante) en el ejecutor propio de transacciones. Un error de la regla de cuentas vuelve como valor y se
    relanza aquí como `ErrorBD`; cualquier otro fallo es `EstadoNoDisponible` (503)."""
    def corre():
        try:
            return ("ok", fn())
        except Exception as e:
            codigo = str(getattr(e, "code", "") or "")
            if codigo in CODIGOS_NEGOCIO:
                return ("bd", codigo)
            raise
    restante = auth_estado._restante()
    if restante <= 0:
        raise EstadoNoDisponible("presupuesto agotado")
    if not _huecos.acquire(blocking=False):   # sin hueco: 503 inmediato, sin encolar
        print(f"[transacciones] Aviso: ejecutor lleno ({operacion})")
        raise EstadoNoDisponible("ejecutor de transacciones lleno")
    try:
        futuro = _ejecutor.submit(corre)
    except BaseException:
        _huecos.release()
        raise EstadoNoDisponible("no se pudo ejecutar")
    futuro.add_done_callback(lambda _f: _huecos.release())   # también ante excepción o cancelación
    try:
        estado, valor = await asyncio.wait_for(asyncio.wrap_future(futuro),
                                               timeout=min(auth_estado.PLAZO_LLAMADA_SEG, restante))
    except asyncio.TimeoutError:
        print(f"[transacciones] Aviso: plazo vencido ({operacion})")
        raise EstadoNoDisponible("plazo vencido")
    except EstadoNoDisponible:
        raise
    except Exception as e:   # el mensaje del servidor puede traer datos: solo el tipo (la cancelación se propaga)
        print(f"[transacciones] Aviso: falló {operacion} ({type(e).__name__})")
        raise EstadoNoDisponible("falló la BD de transacciones")
    if estado == "bd":
        raise ErrorBD(valor)
    return valor
