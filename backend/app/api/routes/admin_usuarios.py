"""
Panel de administración de usuarios del Dueño (CHG-023, CT-013, ADR-012, INV-053 a INV-060).

Todo `/api/v1/admin/*` lo atiende UN despachador ASGI propio que AUTORIZA PRIMERO y valida después:
- No-Dueño (OWNER_EMAIL vacío, sin sesión, sesión inválida o vieja, cuenta suspendida, BD caída o correo distinto), con cualquier
  método y sobre cualquier ruta o parámetro (válido o inválido) → el mismo `HTTPException(404)` que FastAPI produce para una ruta
  inexistente (cuerpo y cabeceras idénticos, SIN `no-store`; nunca 401/403/405/422/429/503). Reutiliza `_confirmar_dueno` del Monitor.
- Solo con el Dueño confirmado valen, en este orden: ruta inexistente (404 normal, sin límite ni `no-store`) → límites (429) →
  método (405) → parámetros (422) → cuerpo con tope real de 2 KB (413/422) → autoprotección (409) → existencia (404) →
  estado (409) → en eliminar: correo de confirmación (422) y contraseña del Dueño (403/429) → acción → 503 si la BD falla.
- `Cache-Control: no-store` en todas las respuestas del Dueño a rutas existentes.
Las respuestas pasan por una lista blanca (`_filtrar_*`, INV-055): nada de hashed_password, session_version ni datos financieros.
La contraseña del Dueño (solo `eliminar`) nunca se escribe en logs, auditoría ni mensajes.
"""
import hmac
import math
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.requests import ClientDisconnect

from app.api.dueno import es_correo_dueno
from app.api.routes import auth as auth_routes
from app.api.routes.monitor import _confirmar_dueno
from app.core.rate_limit import SlidingWindow
from app.models import admin_usuarios as admin_db
from app.models import auth_estado
from app.models.auth_estado import EstadoNoDisponible
from app.models.user import UserDB
from app.schemas import admin_usuarios as esquemas
from app.schemas.admin_usuarios import ParametrosInvalidos

router = APIRouter()

LIMITE_POR_MINUTO = 60
LIMITE_ESCRITURAS_POR_MINUTO = 20
_limite = SlidingWindow(LIMITE_POR_MINUTO, 60)                      # por Dueño; cuentan 200, 405 y 429 (INV-060)
_limite_escrituras = SlidingWindow(LIMITE_ESCRITURAS_POR_MINUTO, 60)   # POST/DELETE
PRESUPUESTO_LIMPIEZA_SEG = 4.0   # presupuesto propio de la limpieza de autenticación tras borrar (best-effort)
_SIN_CACHE = {"Cache-Control": "no-store"}

MSG_429 = "Demasiadas consultas. Intenta de nuevo en un minuto."
MSG_503 = "No se pudo completar la operación. Revisa el estado del usuario antes de reintentar."
MSG_NO_ENCONTRADO = "Usuario no encontrado"
MSG_PROPIA = "No puedes hacerlo sobre tu propia cuenta"
MSG_PENDIENTE = "La cuenta aún no está verificada"
MSG_YA_SUSPENDIDA = "La cuenta ya está suspendida"
MSG_NO_SUSPENDIDA = "La cuenta no está suspendida"
MSG_CORREO = "El correo escrito no coincide con el de la cuenta"
MSG_CONTRASENA = "Contraseña incorrecta"
MSG_413 = "El cuerpo es demasiado grande"

ESTADOS = ("activa", "pendiente", "suspendida")
ACCIONES = ("suspender", "reactivar", "cerrar_sesiones", "eliminar")
_USO_COMPLETO = ("transacciones", "categorias", "presupuestos", "metas", "recurrentes")

# nombre de la ruta → métodos permitidos (el orden es el de la cabecera Allow)
_METODOS = {
    "lista": ("GET",), "detalle": ("GET", "DELETE"), "suspender": ("POST",), "reactivar": ("POST",),
    "cerrar-sesiones": ("POST",), "auditoria": ("GET",),
}


class _Termina(Exception):
    """Corta el flujo con una respuesta ya armada (409, 404 del usuario, 403, 429...)."""

    def __init__(self, respuesta: Response):
        self.respuesta = respuesta


def _json(contenido: Any, status: int = 200, cabeceras: Optional[dict] = None) -> JSONResponse:
    return JSONResponse(contenido, status_code=status, headers={**_SIN_CACHE, **(cabeceras or {})})


def _error(status: int, detalle: str) -> _Termina:
    return _Termina(_json({"detail": detalle}, status))


# ── Lista blanca de salida (INV-055) ──────────────────────────────────────────

def _entero(valor: Any) -> int:
    return valor if type(valor) is int and valor >= 0 else 0


def _texto_o_none(valor: Any) -> Optional[str]:
    return valor if isinstance(valor, str) else None


def _filtrar_usuario(fila: Any, completo: bool) -> dict:
    """Solo las claves de CT-013; lo desconocido se descarta y, si falta lo esencial, 503. El id del Dueño sale como null."""
    if not isinstance(fila, dict):
        raise EstadoNoDisponible("fila inesperada")
    usuario_id, correo, estado = fila.get("id"), fila.get("correo"), fila.get("estado")
    if not isinstance(usuario_id, str) or not isinstance(correo, str) or estado not in ESTADOS:
        raise EstadoNoDisponible("fila sin lo esencial")
    es_dueno = es_correo_dueno(correo)
    origen = fila.get("uso") if isinstance(fila.get("uso"), dict) else {}
    claves = _USO_COMPLETO if completo else ("transacciones",)
    uso: dict[str, Any] = {clave: _entero(origen.get(clave)) for clave in claves}
    if completo:
        uso["whatsapp_conectado"] = origen.get("whatsapp_conectado") is True
    return {
        "id": None if es_dueno else usuario_id,
        "correo": correo,
        "nombre": _texto_o_none(fila.get("nombre")) or "",
        "estado": estado,
        "moneda": _texto_o_none(fila.get("moneda")) or "",
        "registrado_en": _texto_o_none(fila.get("registrado_en")),
        "ultimo_acceso": _texto_o_none(fila.get("ultimo_acceso")),
        "es_dueno": es_dueno,
        "uso": uso,
    }


def _filtrar_registro(fila: Any) -> dict:
    if not isinstance(fila, dict):
        raise EstadoNoDisponible("registro inesperado")
    registro_id, usuario_id, accion = fila.get("id"), fila.get("usuario_id"), fila.get("accion")
    if type(registro_id) is not int or not isinstance(usuario_id, str) or accion not in ACCIONES:
        raise EstadoNoDisponible("registro sin lo esencial")
    return {
        "id": registro_id,
        "fecha": _texto_o_none(fila.get("fecha")),
        "accion": accion,
        "usuario_id": usuario_id,
        "usuario_correo": _texto_o_none(fila.get("usuario_correo")),
    }


def _pagina_de(datos: dict, pagina: int, clave: str, filtro) -> dict:
    total, filas = datos.get("total"), datos.get(clave)
    if type(total) is not int or total < 0 or not isinstance(filas, list):
        raise EstadoNoDisponible("lista inesperada")
    return {
        "generado_en": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pagina": pagina,
        "por_pagina": admin_db.POR_PAGINA,
        "total": total,
        "total_paginas": max(1, math.ceil(total / admin_db.POR_PAGINA)),
        clave: [filtro(f) for f in filas],
    }


# ── Cuerpo con tope real (INV-058) ────────────────────────────────────────────

async def _leer_cuerpo(request: Request) -> bytes:
    """Lee el flujo recibido y corta al pasar de 2 KB: no se confía en `Content-Length`."""
    trozos: list[bytes] = []
    total = 0
    try:
        async for trozo in request.stream():
            total += len(trozo)
            if total > esquemas.CUERPO_MAX_BYTES:
                raise _error(413, MSG_413)
            trozos.append(trozo)
    except ClientDisconnect:
        return b""
    return b"".join(trozos)


# ── Contraseña del Dueño (solo eliminar, INV-058, ADR-012 punto 12) ───────────

async def _comprobar_contrasena_dueno(user_id: str, contrasena: str) -> None:
    """Mismo bloqueo por intentos que el login del Dueño (huella de su correo): 403 genérico si falla (cuenta como fallo),
    429 si está bloqueado, el acierto reinicia la serie. Nunca registra ni devuelve la contraseña."""
    dueno = await UserDB.get_by_id(user_id)
    correo, hashed = (dueno or {}).get("email"), (dueno or {}).get("hashed_password")
    if not correo or not hashed:
        raise EstadoNoDisponible("no se pudo leer la cuenta del Dueño")
    permitido, _hasta = await auth_estado.login_reservar(correo)
    if not permitido:
        raise _error(429, auth_routes._BLOQUEADO_MSG)
    try:
        acierto = await auth_routes.comprobar_contrasena(contrasena, hashed)
    except EstadoNoDisponible:
        await auth_routes.cerrar_reserva_tras_fallo_interno(correo)
        raise
    await auth_estado.login_resolver(correo, acierto)
    if not acierto:
        raise _error(403, MSG_CONTRASENA)


# ── Rutas ─────────────────────────────────────────────────────────────────────

def _identificar(ruta: str) -> Optional[tuple[str, Optional[str]]]:
    """(nombre de la ruta, segmento id) o None si no existe. Sin barra final ni segmentos vacíos."""
    partes = ruta.split("/")
    if partes == ["usuarios"]:
        return "lista", None
    if partes == ["auditoria"]:
        return "auditoria", None
    if len(partes) == 2 and partes[0] == "usuarios" and partes[1]:
        return "detalle", partes[1]
    if len(partes) == 3 and partes[0] == "usuarios" and partes[1] and partes[2] in ("suspender", "reactivar", "cerrar-sesiones"):
        return partes[2], partes[1]
    return None


def _parametros(request: Request, nombre: str) -> list[str]:
    return [v for k, v in request.query_params.multi_items() if k == nombre]


async def _ejecutar_accion(request: Request, user_id: str, nombre: str, id_crudo: str) -> Response:
    usuario_id = esquemas.validar_id(id_crudo)
    if request.method == "GET":
        fila = await admin_db.detalle(usuario_id)
        if fila is None:
            raise _error(404, MSG_NO_ENCONTRADO)
        return _json(_filtrar_usuario(fila, True))

    cuerpo = await _leer_cuerpo(request)   # POST: se ignora; DELETE: se valida
    datos = esquemas.validar_cuerpo_eliminar(cuerpo) if request.method == "DELETE" else None

    # Autoprotección (INV-054): por id de la sesión y, tras leer al objetivo, por su correo; nada se escribe ni se audita
    if nombre != "reactivar" and usuario_id == user_id:
        raise _error(409, MSG_PROPIA)
    actual = await admin_db.detalle(usuario_id)
    if actual is None:
        raise _error(404, MSG_NO_ENCONTRADO)
    correo = actual.get("correo")
    if not isinstance(correo, str):
        raise EstadoNoDisponible("fila sin correo")
    if nombre != "reactivar" and es_correo_dueno(correo):
        raise _error(409, MSG_PROPIA)

    if datos is not None:   # eliminar
        escrito, real = datos.confirmar_correo.strip().lower(), correo.strip().lower()
        if not hmac.compare_digest(escrito.encode("utf-8"), real.encode("utf-8")):
            raise _error(422, MSG_CORREO)
        await _comprobar_contrasena_dueno(user_id, datos.contrasena_dueno)
        resultado = await admin_db.eliminar(usuario_id, correo)
        if resultado == "no_existe":
            raise _error(404, MSG_NO_ENCONTRADO)
        if resultado == "correo_distinto":
            raise _error(422, MSG_CORREO)
        if resultado != "ok":
            raise EstadoNoDisponible("resultado inesperado")
        # Limpieza de intentos y códigos del correo: best-effort, la baja ya está hecha (INV-040: solo un aviso sin datos)
        auth_estado.iniciar_presupuesto(PRESUPUESTO_LIMPIEZA_SEG)
        try:
            await auth_estado.borrar_de_cuenta(correo)
        except Exception as e:
            print(f"[admin] Aviso: no se pudo limpiar el estado de autenticación tras la baja ({type(e).__name__})")
        return Response(status_code=204, headers=_SIN_CACHE)

    accion = {"suspender": admin_db.suspender, "reactivar": admin_db.reactivar,
              "cerrar-sesiones": admin_db.cerrar_sesiones}[nombre]
    resultado = await accion(usuario_id)
    if resultado == "no_existe":
        raise _error(404, MSG_NO_ENCONTRADO)
    if resultado == "ya":
        raise _error(409, MSG_YA_SUSPENDIDA)
    if resultado == "pendiente":
        raise _error(409, MSG_PENDIENTE)
    if resultado == "no_suspendida":
        raise _error(409, MSG_NO_SUSPENDIDA)
    if resultado != "ok":
        raise EstadoNoDisponible("resultado inesperado")
    nuevo = await admin_db.detalle(usuario_id)
    if nuevo is None:
        raise _error(404, MSG_NO_ENCONTRADO)
    return _json(_filtrar_usuario(nuevo, True))


async def _atender(request: Request, user_id: str, nombre: str, id_crudo: Optional[str]) -> Response:
    if nombre == "lista":
        pagina = esquemas.validar_pagina(_parametros(request, "pagina"))
        q = esquemas.validar_q(_parametros(request, "q"))
        return _json(_pagina_de(await admin_db.listar(q, pagina), pagina, "usuarios", lambda f: _filtrar_usuario(f, False)))
    if nombre == "auditoria":
        pagina = esquemas.validar_pagina(_parametros(request, "pagina"))
        return _json(_pagina_de(await admin_db.auditoria(pagina), pagina, "registros", _filtrar_registro))
    return await _ejecutar_accion(request, user_id, nombre, id_crudo or "")


async def atender(request: Request) -> Response:
    # 1. AUTORIZAR PRIMERO (INV-053): cualquier fallo es el 404 estándar; ni validación ni límites ni cuerpo antes
    user_id = await _confirmar_dueno(request.headers.get("authorization"))
    auth_estado.iniciar_presupuesto()

    # 2. Ya es el Dueño. Una ruta que no existe es el 404 normal de la API (sin `no-store`, sin límite)
    ruta = _identificar(request.path_params.get("ruta", ""))
    if ruta is None:
        raise HTTPException(status_code=404)
    nombre, id_crudo = ruta

    if not _limite.hit(user_id):
        return _json({"detail": MSG_429}, 429)
    if request.method in ("POST", "DELETE") and not _limite_escrituras.hit(user_id):
        return _json({"detail": MSG_429}, 429)
    if request.method not in _METODOS[nombre]:
        return _json({"detail": "Método no permitido"}, 405, {"Allow": ", ".join(_METODOS[nombre])})

    try:
        return await _atender(request, user_id, nombre, id_crudo)
    except _Termina as t:
        return t.respuesta
    except ParametrosInvalidos as e:
        return _json({"detail": str(e)}, 422)
    except Exception as e:   # fail-closed: nada del servidor sale en la respuesta ni en el log
        print(f"[admin] Aviso: operación fallida ({type(e).__name__})")
        return _json({"detail": MSG_503}, 503)


class _RutaCualquierMetodo:
    """App ASGI (no una función): Starlette no le impone «solo GET» y responde a cualquier método; `atender` decide entre
    404, 405 y el resto (igual que el Monitor)."""

    async def __call__(self, scope, receive, send) -> None:
        respuesta = await atender(Request(scope, receive, send))
        await respuesta(scope, receive, send)


# Todo lo que cuelga de /admin (existente o no) pasa por el despachador: así la autorización va siempre primero
router.add_route("/{ruta:path}", _RutaCualquierMetodo(), methods=None, include_in_schema=False)
