"""
Exportar transacciones a CSV o Excel (CHG-018, CT-011, UC-015, ADR-011).

- El usuario sale SIEMPRE de la sesión (INV-001, INV-042); no hay parámetro de usuario.
- Solo lectura. La lectura paginada y la generación corren en un hilo (REQ-N-026) con plazo total de 8 s.
- Límite: 10 descargas por minuto por usuario (en memoria, como los demás límites de costo, INV-024).
"""
import asyncio
import functools
import threading
from typing import Optional

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse, Response

from app.api.sesion import usuario_de_sesion
from app.core.rate_limit import SlidingWindow
from app.models.plataapp import TransaccionDB
from app.schemas.exportar import ParametrosInvalidos, validar_consulta
from app.utils import exportar as generador

router = APIRouter()

_por_minuto = SlidingWindow(limit=10, window_seconds=60)

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
    usuario_id = await usuario_de_sesion(authorization)   # 401/503 (CT-002); cualquier otro dato de usuario se ignora
    try:
        consulta = validar_consulta(desde, hasta, formato)
    except ParametrosInvalidos as e:
        return _error(422, str(e))
    if not _por_minuto.hit(usuario_id):
        return _error(429, _MSG_429)

    detener = threading.Event()

    def trabajo() -> bytes:
        categorias = TransaccionDB.nombres_de_categorias_propias(usuario_id)
        leer = functools.partial(TransaccionDB.pagina_para_exportar, usuario_id, consulta.desde, consulta.hasta)
        return generador.generar_archivo(consulta.formato, leer, categorias, detener, generador.PLAZO_SEGUNDOS)

    try:
        archivo = await asyncio.wait_for(asyncio.to_thread(trabajo), timeout=generador.PLAZO_SEGUNDOS)
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
