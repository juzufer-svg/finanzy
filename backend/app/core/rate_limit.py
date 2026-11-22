"""
Limitadores de frecuencia en memoria (ventana deslizante).

Protegen los endpoints que envían correos o verifican credenciales frente a
abuso automatizado. Viven en memoria del proceso: se reinician con cada
despliegue, lo cual es aceptable para una sola instancia del backend.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


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
