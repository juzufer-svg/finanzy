"""
Exportar transacciones a CSV o Excel (CHG-018, CT-011, UC-015, ADR-011).

- El usuario sale SIEMPRE de la sesión (INV-001, INV-042); no hay parámetro de usuario.
- Solo lectura. La lectura paginada y la generación corren en un hilo (REQ-N-026) con plazo total de 8 s.
- Como máximo `MAX_EXPORTACIONES_SIMULTANEAS` (2) exportaciones a la vez, en un ejecutor PROPIO (no el compartido del
  servidor): si está lleno, 503 inmediato SIN encolar (mismo patrón que `auth_estado.ejecutar_bcrypt`, INV-044).
- Límite: 10 descargas por minuto por usuario (en memoria, como los demás límites de costo, INV-024).
"""
import asyncio
import functools
import threading
from typing import Optional

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from app.api.sesion import usuario_de_sesion
from app.core.rate_limit import SlidingWindow
from app.models.plataapp import TransaccionDB
from app.schemas.exportar import ParametrosInvalidos, validar_consulta
from app.utils import exportar as generador

router = APIRouter()

_por_minuto = SlidingWindow(limit=10, window_seconds=60)

MAX_EXPORTACIONES_SIMULTANEAS = 2
_ranuras = threading.BoundedSemaphore(MAX_EXPORTACIONES_SIMULTANEAS)   # se libera cuando el HILO termina, no al vencer el plazo
_ejecutor = ThreadPoolExecutor(max_workers=MAX_EXPORTACIONES_SIMULTANEAS, thread_name_prefix="exportar")

_CABECERAS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
_MSG_429 = "Demasiadas descargas. Espera un momento e intenta de nuevo."
_MSG_503 = "Servicio no disponible. Intenta de nuevo en unos minutos."
_MSG_LENTA = "La exportación tardó demasiado. Elige menos meses."
_MSG_FILAS = "Hay más de 10 000 transacciones en ese rango. Elige menos meses."
_MSG_BYTES = "El archivo superaría los 4 MB. Elige menos meses."


def _error(status: int, detalle: str, codigo: Optional[str] = None) -> JSONResponse:
    cuerpo = {"detail": detalle}
    if codigo:
        cuerpo["codigo"] = codigo
    return JSONResponse(status_code=status, content=cuerpo, headers=_CABECERAS)


@router.get("/exportaciones/transacciones")
async def exportar_transacciones(
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    formato: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    try:
        usuario_id = await usuario_de_sesion(authorization)   # 401/503 (CT-002); cualquier otro dato de usuario se ignora
    except HTTPException as e:   # también el 401/503 de la sesión va sin caché y con nosniff (llamadas directas al backend)
        return _error(e.status_code, str(e.detail))
    try:
        consulta = validar_consulta(desde, hasta, formato)
    except ParametrosInvalidos as e:
        return _error(422, str(e))
    if not _por_minuto.hit(usuario_id):
        return _error(429, _MSG_429)

    if not _ranuras.acquire(blocking=False):   # lleno: se rechaza al instante, nunca se encola ni se acumula trabajo
        print("[exportar] Aviso: ejecutor de exportaciones lleno")
        return _error(503, _MSG_503)
    detener = threading.Event()

    def trabajo() -> bytes:
        categorias = TransaccionDB.nombres_de_categorias_propias(usuario_id)
        leer = functools.partial(TransaccionDB.pagina_para_exportar, usuario_id, consulta.desde, consulta.hasta)
        return generador.generar_archivo(consulta.formato, leer, categorias, detener, generador.PLAZO_SEGUNDOS)

    try:
        futuro = _ejecutor.submit(trabajo)
    except Exception:
        _ranuras.release()
        return _error(503, _MSG_503)
    futuro.add_done_callback(lambda _f: _ranuras.release())
    try:
        archivo = await asyncio.wait_for(asyncio.wrap_future(futuro), timeout=generador.PLAZO_SEGUNDOS)
    except asyncio.TimeoutError:
        detener.set()   # el hilo termina en la siguiente comprobación; nunca se entrega un archivo parcial
        return _error(503, _MSG_LENTA)
    except generador.ExportacionLenta:
        return _error(503, _MSG_LENTA)
    except generador.ExportacionDemasiadasFilas:
        return _error(422, _MSG_FILAS, "exportacion_demasiadas_filas")
    except generador.ExportacionDemasiadoGrande:
        return _error(422, _MSG_BYTES, "exportacion_demasiado_grande")
    except Exception as e:   # la BD falló (INV-013): se propaga como 503 sin archivo parcial y sin filtrar detalles
        print(f"[exportar] Error al generar el archivo ({type(e).__name__})")
        return _error(503, _MSG_503)

    tipo = generador.TIPO_XLSX if consulta.formato == "xlsx" else generador.TIPO_CSV
    return Response(content=archivo, media_type=tipo, headers={
        **_CABECERAS,
        "Content-Disposition": f'attachment; filename="{consulta.nombre_archivo}"',
    })
