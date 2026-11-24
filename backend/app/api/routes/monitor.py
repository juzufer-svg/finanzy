"""
Monitor de consumos del Dueño (CHG-017, CT-010, ADR-008, INV-031 a INV-036).

`GET /api/v1/monitor/resumen`: solo lectura y solo para el Dueño (correo de la sesión = OWNER_EMAIL).

Autorización por petición, en este orden y fail-closed (INV-031):
1. OWNER_EMAIL vacío → 404.   2. Sesión inválida o BD caída al verificarla → 404.   3. Correo distinto → 404.
4. Solo ahora se sabe que es el Dueño: límite 20/min (429), método (405 si no es GET), contadores (503 si fallan).
El 404 es el mismo `HTTPException(404)` que produce FastAPI para una ruta inexistente: mismo cuerpo
(`{"detail": "Not Found"}`) y mismas cabeceras, SIN `Cache-Control: no-store`. El `no-store` solo va en las
respuestas al Dueño confirmado (200, 405, 429 y 503).
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.dueno import es_correo_dueno
from app.core.config import settings
from app.api.sesion import usuario_de_sesion
from app.core.rate_limit import SlidingWindow
from app.models import contadores
from app.models.user import UserDB
from app.utils import monitor_plataformas

router = APIRouter()

LIMITE_POR_MINUTO = 20
_limite = SlidingWindow(LIMITE_POR_MINUTO, 60)   # por Dueño; cuentan 200, 405 y 429 (INV-035)
PLAZO_CONTADORES = 5.0   # segundos: plazo total de la lectura de contadores (503 solo al Dueño)
_SIN_CACHE = {"Cache-Control": "no-store"}


def _no_encontrado() -> HTTPException:
    # Idéntico al 404 de una ruta inexistente (INV-031): nada que delate el Monitor ni al Dueño
    return HTTPException(status_code=404)


async def _confirmar_dueno(authorization: Optional[str]) -> str:
    """Devuelve el id del Dueño o lanza el 404 estándar ante CUALQUIER fallo (fail-closed)."""
    if not settings.OWNER_EMAIL:   # sin OWNER_EMAIL nadie es Dueño: ni se mira la sesión
        raise _no_encontrado()
    try:
        user_id = await usuario_de_sesion(authorization)
        user = await UserDB.get_by_id(user_id)
        correo = user.get("email") if isinstance(user, dict) else None
    except Exception:
        raise _no_encontrado()
    if not es_correo_dueno(correo):
        raise _no_encontrado()
    return user_id


def _leer_contadores() -> tuple[list[dict], Optional[str]]:
    return contadores.leer_ventana(), contadores.fecha_mas_antigua()


def _numero(valor: Any) -> int:
    return valor if type(valor) is int and valor > 0 else 0


def construir_contadores(filas: list[dict], desde: Optional[str]) -> dict:
    """Agrega las filas por día de Colombia (CT-010): solo días con algún contador, orden ascendente, claves fijas."""
    dias: dict[str, dict] = {}
    for fila in filas:
        if not isinstance(fila, dict):
            continue
        fecha, metrica, origen, cantidad = fila.get("fecha"), fila.get("metrica"), fila.get("origen"), _numero(fila.get("cantidad"))
        if metrica not in contadores.METRICAS or not isinstance(fecha, str):
            continue   # la marca de purga y cualquier otra métrica nunca se exponen
        dia = dias.setdefault(fecha, {
            "fecha": fecha,
            "claude": {o: {"llamadas": 0, "tokens_entrada": 0, "tokens_salida": 0} for o in contadores.ORIGENES_CLAUDE},
            "brevo_correos_enviados": 0,
            "whatsapp_mensajes": {"enviados": 0, "recibidos": 0},
        })
        if metrica.startswith("claude_"):
            if origen in contadores.ORIGENES_CLAUDE:
                campo = {"claude_llamadas": "llamadas", "claude_tokens_entrada": "tokens_entrada",
                         "claude_tokens_salida": "tokens_salida"}[metrica]
                dia["claude"][origen][campo] += cantidad
        elif metrica == "brevo_correos_enviados":
            dia["brevo_correos_enviados"] += cantidad
        elif metrica == "whatsapp_enviados":
            dia["whatsapp_mensajes"]["enviados"] += cantidad
        elif metrica == "whatsapp_recibidos":
            dia["whatsapp_mensajes"]["recibidos"] += cantidad
    return {"desde": desde, "dias": [dias[f] for f in sorted(dias)]}


async def resumen(request: Request):
    # Se registra para CUALQUIER método (abajo): así TRACE, PROPFIND, OPTIONS sin preflight, etc. pasan primero
    # por la autorización y el no-Dueño recibe el mismo 404 que una ruta inexistente (INV-031). El preflight CORS
    # real (con Origin y Access-Control-Request-Method) lo atiende el middleware antes de llegar aquí.
    user_id = await _confirmar_dueno(request.headers.get("authorization"))

    # Ya es el Dueño: ahora sí valen 429, 405 y 503 (todas con no-store)
    if not _limite.hit(user_id):
        return JSONResponse({"detail": "Demasiadas consultas. Intenta de nuevo en un minuto."},
                            status_code=429, headers=_SIN_CACHE)
    if request.method != "GET":
        return JSONResponse({"detail": "Método no permitido"}, status_code=405,
                            headers={**_SIN_CACHE, "Allow": "GET"})

    # Contadores y plataformas en paralelo (INV-034): el peor caso es el plazo de 5 s de una plataforma
    lectura, plataformas = await asyncio.gather(
        asyncio.wait_for(asyncio.to_thread(_leer_contadores), timeout=PLAZO_CONTADORES),
        monitor_plataformas.consultar_todas(), return_exceptions=True,
    )
    if isinstance(lectura, BaseException):
        print(f"[monitor] No se pudieron leer los contadores ({type(lectura).__name__})")
        return JSONResponse({"detail": "No se pudo leer el Monitor. Intenta de nuevo en unos minutos."},
                            status_code=503, headers=_SIN_CACHE)
    if isinstance(plataformas, BaseException):   # consultar_todas no lanza; por si acaso
        plataformas = {n: {"estado": "no_disponible", "datos": None, "actualizado_en": None}
                       for n in monitor_plataformas.PLATAFORMAS}
    filas, desde = lectura
    return JSONResponse(
        {
            "generado_en": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "contadores": construir_contadores(filas, desde),
            "plataformas": plataformas,
        },
        headers=_SIN_CACHE,
    )


class _RutaCualquierMetodo:
    """App ASGI: como NO es una función, Starlette no le impone «solo GET» y la ruta responde a cualquier método
    (TRACE, PROPFIND, OPTIONS sin preflight, inventados...). `resumen` decide entre 404 y 405."""

    async def __call__(self, scope, receive, send) -> None:
        respuesta = await resumen(Request(scope, receive, send))
        await respuesta(scope, receive, send)


router.add_route("/resumen", _RutaCualquierMetodo(), methods=None, include_in_schema=False)
