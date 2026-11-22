"""
Asistente con Claude (CHG-010, CT-007): preguntas en lenguaje natural sobre las finanzas propias.

Topes de costo (INV-024): sin ANTHROPIC_API_KEY responde 503 sin llamar a nadie; por usuario,
5 preguntas por minuto y ASISTENTE_PREGUNTAS_POR_USUARIO_DIA al día; en total,
ASISTENTE_PREGUNTAS_TOTALES_DIA al día. Los límites viven en memoria (como los de rate_limit.py)
y se reinician con cada despliegue.
"""
from fastapi import APIRouter, Header, HTTPException

from app.api.sesion import usuario_de_sesion
from app.core.config import settings
from app.core.rate_limit import SlidingWindow, enforce
from app.schemas.asistente import PreguntaAsistente, RespuestaAsistente
from app.utils import asistente

router = APIRouter()

_DIA = 24 * 60 * 60
_por_minuto = SlidingWindow(limit=5, window_seconds=60)
_por_usuario_dia = SlidingWindow(limit=max(1, settings.ASISTENTE_PREGUNTAS_POR_USUARIO_DIA), window_seconds=_DIA)
_global_dia = SlidingWindow(limit=max(1, settings.ASISTENTE_PREGUNTAS_TOTALES_DIA), window_seconds=_DIA)

NO_CONFIGURADO = "El asistente no está disponible: falta configurarlo en el servidor."


@router.post("/chat", response_model=RespuestaAsistente)
async def preguntar(datos: PreguntaAsistente, authorization: str = Header(...)):
    usuario_id = await usuario_de_sesion(authorization)
    if not settings.ANTHROPIC_API_KEY.strip():
        raise HTTPException(status_code=503, detail=NO_CONFIGURADO)

    enforce(_por_minuto, usuario_id, "Vas muy rápido. Espera un momento antes de preguntar de nuevo.")
    if not _por_usuario_dia.allowed(usuario_id):
        raise HTTPException(status_code=429, detail="Llegaste al límite de preguntas de hoy. Vuelve mañana.")
    enforce(_global_dia, "global", "El asistente alcanzó su límite diario. Vuelve mañana.")
    _por_usuario_dia.hit(usuario_id)

    try:
        return await asistente.responder(
            usuario_id, datos.pregunta.strip(), [m.model_dump() for m in datos.historial]
        )
    except asistente.AsistenteError as e:
        raise HTTPException(status_code=e.status, detail=e.detalle)
