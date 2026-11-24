"""
Limitadores de frecuencia (ventana deslizante): `SlidingWindow` en memoria y `VentanaPersistente` (auth, CHG-020).

Protegen los endpoints que envían correos o verifican credenciales frente a
abuso automatizado. Viven en memoria del proceso: se reinician con cada
despliegue, lo cual es aceptable para una sola instancia del backend.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.models import auth_estado


class SlidingWindow:
    """Permite como máximo `limit` eventos por clave dentro de `window_seconds`."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, deque] = defaultdict(deque)

    def _count(self, key: str, now: float) -> int:
        events = self._events.get(key)
        if not events:
            return 0
        while events and now - events[0] >= self.window:
            events.popleft()
        if not events:
            # no acumular claves vacías indefinidamente
            del self._events[key]
            return 0
        return len(events)

    def allowed(self, key: str) -> bool:
        """True si todavía queda cupo (no registra el evento)."""
        return self._count(key, time.monotonic()) < self.limit

    def hit(self, key: str) -> bool:
        """Registra el evento si hay cupo. Devuelve False si se superó el límite."""
        now = time.monotonic()
        if self._count(key, now) >= self.limit:
            return False
        self._events[key].append(now)
        return True

    def reset(self) -> None:
        self._events.clear()


def client_ip(request: Request) -> str:
    """IP del cliente.

    El tráfico normal llega a través del proxy de Vercel, que reemplaza
    X-Forwarded-For con la IP real del visitante; el primer valor es el cliente.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def enforce(limiter: SlidingWindow, key: str, detail: str) -> None:
    """Lanza 429 si `key` superó el límite de `limiter`."""
    if not limiter.hit(key):
        raise HTTPException(status_code=429, detail=detail)


class VentanaPersistente:
    """Ventana deslizante POR IP persistida en PostgreSQL (CHG-020, INV-037/INV-039/INV-040), solo para los usos de
    autenticación (register, login, verify, resend, forgot, reset y cambio de contraseña). No sustituye a
    `SlidingWindow`, que sigue siendo el de los demás usos (asistente, WhatsApp, Monitor; BL-040).

    La IP llega a la BD solo como huella HMAC. Un fallo de la BD de estado lanza `auth_estado.EstadoNoDisponible`
    (las rutas responden 503: nunca se deja pasar)."""

    def __init__(self, tipo: str, limit: int, window_seconds: int):
        self.tipo = tipo
        self.limit = limit
        self.window = window_seconds

    async def hit(self, ip: str) -> str:
        """Registra el evento si hay cupo: 'ok' | 'limitado' | 'lleno'."""
        return await auth_estado.limite_registrar(ip, self.tipo, self.limit, self.window)


# Mismos números que INV-010: 10 pedidos de código por IP/hora y 30 intentos de credenciales/códigos por IP/10 min
ip_pedidos_codigo = VentanaPersistente("ip_pedidos_codigo", limit=10, window_seconds=3600)
ip_intentos_auth = VentanaPersistente("ip_intentos_auth", limit=30, window_seconds=600)


async def enforce_persistente(limiter: VentanaPersistente, request: Request, detail: str) -> None:
    """429 si la IP superó el límite; 429 también si la tabla de eventos llegó a su tope (IP falsificadas, INV-040,
    con un aviso sin datos personales). Un fallo de la BD de estado se propaga como `EstadoNoDisponible`."""
    resultado = await limiter.hit(client_ip(request))
    if resultado == "ok":
        return
    if resultado == "lleno":
        print("[rate_limit] Aviso: la tabla de eventos de límites llegó a su tope; se responde 429 por IP")
    raise HTTPException(status_code=429, detail=detail)
