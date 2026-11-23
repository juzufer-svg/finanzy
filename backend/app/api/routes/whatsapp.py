"""
WhatsApp con IA (CHG-014, CT-009).

- `GET  /whatsapp/webhook`: verificación de Meta (hub.verify_token → hub.challenge).
- `POST /whatsapp/webhook`: mensajes entrantes. Exige la firma X-Hub-Signature-256; responde 200 de
  inmediato y procesa en segundo plano (Meta reintenta si tarda o falla, y eso duplicaría).
- `GET/POST/DELETE /whatsapp/enlace`: desde la app (con sesión) ver, generar el código y quitar el enlace.

Topes (INV-030): por número, 10 mensajes por minuto; por usuario, WHATSAPP_MENSAJES_POR_DIA (50) al día;
en total, WHATSAPP_MENSAJES_TOTALES_DIA (300). Intentos de código desde números no enlazados: 5 por hora.
"""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.api.sesion import usuario_de_sesion
from app.core.config import settings
from app.core.rate_limit import SlidingWindow
from app.models.whatsapp import WhatsappDB
from app.utils import whatsapp

router = APIRouter()

_DIA = 24 * 60 * 60
_por_minuto = SlidingWindow(limit=10, window_seconds=60)
_por_usuario_dia = SlidingWindow(limit=max(1, settings.WHATSAPP_MENSAJES_POR_DIA), window_seconds=_DIA)
_global_dia = SlidingWindow(limit=max(1, settings.WHATSAPP_MENSAJES_TOTALES_DIA), window_seconds=_DIA)
_intentos_codigo = SlidingWindow(limit=5, window_seconds=60 * 60)
_avisado_limite: set[str] = set()   # para avisar del tope una sola vez por día (no gastar respuestas)

LIMITE_DIA = ("Llegaste al límite de {n} mensajes en las últimas 24 horas. Vuelve en unas horas o registra "
              "desde la app.")
LIMITE_GLOBAL = "El registro por WhatsApp alcanzó su límite diario. Vuelve en unas horas o registra desde la app."
ERROR_GENERAL = "⚠️ No pude completar lo que pediste por un error del servidor. Revisa en la app si quedó registrado."


@router.get("/webhook")
async def verificar_webhook(
    modo: Optional[str] = Query(None, alias="hub.mode"),
    token: Optional[str] = Query(None, alias="hub.verify_token"),
    reto: Optional[str] = Query(None, alias="hub.challenge"),
):
    if modo == "subscribe" and reto is not None and whatsapp.token_de_verificacion_valido(token):
        return PlainTextResponse(reto)
    raise HTTPException(status_code=403, detail="Verificación inválida")


@router.post("/webhook")
async def recibir_webhook(request: Request, background_tasks: BackgroundTasks):
    cuerpo = await request.body()
    if not whatsapp.firma_valida(cuerpo, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=403, detail="Firma inválida")
    try:
        payload = await request.json()
    except ValueError:
        return {"ok": True}
    for mensaje in whatsapp.mensajes_de_texto(payload):
        background_tasks.add_task(procesar_mensaje, mensaje)
    return {"ok": True}


async def procesar_mensaje(mensaje: dict) -> None:
    """Procesa un mensaje entrante. Nunca lanza: los errores se registran sin datos sensibles y se avisa
    a la persona (revisión CHG-014, H3) solo si su número está enlazado o si enviaba un código de enlace."""
    try:
        await _procesar(mensaje)
    except Exception as e:
        print(f"[whatsapp] Error procesando un mensaje ({type(e).__name__})")
        if mensaje.get("avisar_error"):
            try:
                await whatsapp.enviar(mensaje["de"], ERROR_GENERAL)
            except Exception:
                pass


async def _procesar(mensaje: dict) -> None:
    telefono, texto, wamid = mensaje["de"], mensaje.get("texto"), mensaje["id"]
    usuario_id = await WhatsappDB.usuario_de_telefono(telefono)
    es_codigo = bool(texto and whatsapp.CODIGO.match(texto))
    if not usuario_id and not es_codigo:
        return  # número no enlazado: se ignora en silencio, sin guardar nada (no gasta IA ni respuestas)
    if es_codigo and not _intentos_codigo.allowed(telefono):
        return

    # Idempotencia: Meta puede reenviar el mismo mensaje (INV-029)
    if not await WhatsappDB.marcar_procesado(wamid, usuario_id):
        return
    mensaje["avisar_error"] = True

    # Código de enlace: lo único que acepta un número desconocido (nunca llega a la IA)
    if es_codigo:
        _intentos_codigo.hit(telefono)
        dueno = whatsapp.usar_codigo(texto)
        if dueno:
            await WhatsappDB.enlazar(dueno, telefono)
            await whatsapp.enviar(telefono, "✅ ¡Listo! Tu WhatsApp quedó conectado a Finanzy.\n\n" + whatsapp.AYUDA)
        else:
            await whatsapp.enviar(telefono, "Ese código no es válido o ya venció. Genera uno nuevo en Finanzy → Perfil → WhatsApp.")
        return

    # Tope por minuto antes de responder cualquier cosa (también «ayuda» y lo que no es texto, INV-030)
    if not _por_minuto.allowed(telefono):
        return
    _por_minuto.hit(telefono)
    if not texto:
        await whatsapp.enviar(telefono, "Por ahora solo entiendo mensajes de texto. " + whatsapp.AYUDA.split("\n")[0])
        return
    if whatsapp.es_ayuda(texto):   # sin IA y sin gastar el cupo diario (revisión CHG-014, H5)
        await whatsapp.enviar(telefono, whatsapp.AYUDA)
        return

    propio_agotado = not _por_usuario_dia.allowed(usuario_id)
    if propio_agotado or not _global_dia.allowed("global"):
        if usuario_id not in _avisado_limite:
            _avisado_limite.add(usuario_id)
            aviso = LIMITE_DIA.format(n=settings.WHATSAPP_MENSAJES_POR_DIA) if propio_agotado else LIMITE_GLOBAL
            await whatsapp.enviar(telefono, aviso)
        return
    _avisado_limite.discard(usuario_id)
    _por_usuario_dia.hit(usuario_id)
    _global_dia.hit("global")

    if not settings.ANTHROPIC_API_KEY.strip():
        await whatsapp.enviar(telefono, "⚠️ La IA no está configurada en el servidor. No se registró nada.")
        return
    respuesta = await whatsapp.responder(usuario_id, texto, wamid)
    await whatsapp.enviar(telefono, respuesta)


# ==================== Enlace desde la app (con sesión) ====================

def _oculto(telefono: Optional[str]) -> Optional[str]:
    return f"•••• {telefono[-4:]}" if telefono else None


@router.get("/enlace")
async def ver_enlace(authorization: str = Header(...)):
    usuario_id = await usuario_de_sesion(authorization)
    telefono = await WhatsappDB.telefono_de_usuario(usuario_id)
    return {"configurado": whatsapp.configurado(), "enlazado": bool(telefono), "telefono": _oculto(telefono)}


@router.post("/enlace")
async def generar_codigo(authorization: str = Header(...)):
    usuario_id = await usuario_de_sesion(authorization)
    if not whatsapp.configurado():
        raise HTTPException(status_code=503, detail="WhatsApp no está configurado en el servidor todavía.")
    return {"codigo": whatsapp.nuevo_codigo(usuario_id), "vence_en_minutos": whatsapp.CODIGO_MINUTOS}


@router.delete("/enlace")
async def quitar_enlace(authorization: str = Header(...)):
    usuario_id = await usuario_de_sesion(authorization)
    await WhatsappDB.desenlazar(usuario_id)
    return {"message": "WhatsApp desconectado"}
