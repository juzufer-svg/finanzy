"""
Lectura de los consumos de las plataformas para el Monitor del Dueño (CHG-017, CT-010, ADR-008).

Un cliente por plataforma (Railway, Anthropic, Meta, Supabase, Vercel y Brevo). Reglas de seguridad:
- INV-034: hosts y rutas FIJOS en este archivo; la configuración solo aporta ids, validados con una regex
  estricta antes de componer la URL; nada de la petición del cliente llega aquí; httpx NO sigue redirecciones;
  plazo TOTAL de 5 s por plataforma con `asyncio.wait_for`; las seis se consultan en paralelo.
- INV-035: caché en memoria de 60 s por plataforma (los fallos, 15 s).
- INV-032: solo se devuelven campos de la lista blanca (números finitos no negativos, fechas ISO UTC con «Z»,
  cadenas de la lista). Cualquier error, token faltante o respuesta rara → `no_disponible`, SIN motivo; el log
  lleva el nombre de la plataforma, el TIPO de la excepción y un motivo de lista cerrada (`MOTIVOS`), nunca
  URL, cabeceras, cuerpo, mensaje ni token.
- INV-033: solo lectura (GET; Railway usa GraphQL por POST pero solo con una consulta `query`).
- Solo se usan los tokens MONITOR_*; nunca los de escritura (WHATSAPP_TOKEN, BREVO_API_KEY, SUPABASE_KEY,
  ANTHROPIC_API_KEY).
"""
from __future__ import annotations

import asyncio
import calendar
import json
import math
import re
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Optional

import httpx

from app.core.config import settings

PLATAFORMAS = ("railway", "anthropic", "meta", "supabase", "vercel", "brevo")

TIMEOUT_TOTAL = 5.0        # segundos, por plataforma, plazo TOTAL (INV-034)
CACHE_OK = 60.0            # segundos (INV-035)
CACHE_FALLO = 15.0         # segundos (INV-035)
MAX_CUERPO = 1_000_000     # bytes: un cuerpo de plataforma mayor se descarta (no_disponible)

# URLs FIJAS (INV-034). Los únicos fragmentos variables son ids de configuración ya validados.
URL_RAILWAY = "https://backboard.railway.com/graphql/v2"
URL_ANTHROPIC_USO = "https://api.anthropic.com/v1/organizations/usage_report/messages"
URL_ANTHROPIC_COSTO = "https://api.anthropic.com/v1/organizations/cost_report"
URL_META = "https://graph.facebook.com/{version}/{waba}"
URL_VERCEL_EQUIPO = "https://api.vercel.com/v2/teams/{team}"
URL_BREVO_CUENTA = "https://api.brevo.com/v3/account"
URL_BREVO_REPORTE = "https://api.brevo.com/v3/smtp/statistics/aggregatedReport"

# Formatos estrictos de los ids de configuración (sin «/», «.», «?», «#», espacios...)
_RE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_RE_VERSION_GRAPH = re.compile(r"^v\d{1,2}\.\d{1,2}$")
_RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_INSTANTE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PREFIJO_ADMIN_ANTHROPIC = "sk-ant-admin"

# Lista blanca por plataforma (CT-010): clave → "num" | "fecha" | tupla de cadenas permitidas
ESQUEMA: dict[str, dict[str, Any]] = {
    "railway": {"costo_estimado_mes": "num", "uso_cpu_vcpu_horas": "num", "uso_memoria_gb_horas": "num",
                "creditos_saldo": "num", "moneda": ("USD",), "periodo_hasta": "fecha"},
    "anthropic": {"costo_mes": "num", "moneda": ("USD",), "tokens_entrada_mes": "num", "tokens_salida_mes": "num"},
    "meta": {"conversaciones_periodo": "num", "periodo_desde": "fecha", "periodo_hasta": "fecha"},
    "supabase": {"tamano_bd_bytes": "num", "limite_bd_bytes": "num"},
    "vercel": {"plan": ("gratuito", "pro", "otro"), "ancho_banda_bytes": "num", "limite_ancho_banda_bytes": "num"},
    "brevo": {"creditos_restantes": "num", "enviados_hoy": "num"},
}

_reloj: Callable[[], float] = time.monotonic          # sustituible en las pruebas (caché)
_cache: dict[str, tuple[float, dict]] = {}            # plataforma → (expira, resultado)


# Motivos de lista CERRADA para el log de diagnóstico (nunca salen al cliente, INV-032)
MOTIVOS = frozenset({
    "http_401", "http_403", "http_404", "http_429", "http_5xx", "http_otro", "redireccion", "cuerpo_grande",
    "json_invalido", "graphql_errors", "forma_inesperada", "token_vacio", "id_invalido", "sin_campos",
    "config_invalida",
})


class _NoDisponible(Exception):
    """Interna: la plataforma no se puede consultar. Nunca sale al cliente. Al log solo llega, como mucho,
    un `motivo` de la lista cerrada `MOTIVOS` (nunca cuerpos, mensajes, URLs, cabeceras ni tokens)."""

    def __init__(self, motivo: Optional[str] = None):
        super().__init__()
        self.motivo = motivo if motivo in MOTIVOS else None


def _motivo_http(codigo: int) -> str:
    if 300 <= codigo < 400:
        return "redireccion"
    if codigo in (401, 403, 404, 429):
        return f"http_{codigo}"
    if 500 <= codigo < 600:
        return "http_5xx"
    return "http_otro"


def _no_disponible() -> dict:
    return {"estado": "no_disponible", "datos": None, "actualizado_en": None}


def _iso_utc(momento: Optional[datetime] = None) -> str:
    return (momento or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hoy() -> date:
    return datetime.now(timezone.utc).date()


# ==================== LISTA BLANCA (INV-032) ====================

def _numero_valido(valor: Any) -> bool:
    return type(valor) in (int, float) and math.isfinite(valor) and valor >= 0   # nunca bool


def _fecha_valida(valor: Any) -> bool:
    if not isinstance(valor, str):
        return False
    try:
        if _RE_FECHA.match(valor):
            date.fromisoformat(valor)
            return True
        if _RE_INSTANTE.match(valor):
            datetime.strptime(valor, "%Y-%m-%dT%H:%M:%SZ")
            return True
    except ValueError:
        return False
    return False


def filtrar(plataforma: str, crudo: Any) -> Optional[dict]:
    """Deja solo las claves de la lista blanca con valores válidos. None si no queda ningún campo."""
    esquema = ESQUEMA.get(plataforma, {})
    if not isinstance(crudo, dict):
        return None
    limpio: dict[str, Any] = {}
    for clave, regla in esquema.items():
        if clave not in crudo:
            continue
        valor = crudo[clave]
        if regla == "num":
            if _numero_valido(valor):
                limpio[clave] = round(valor, 4) if type(valor) is float else valor
        elif regla == "fecha":
            if _fecha_valida(valor):
                limpio[clave] = valor
        elif isinstance(regla, tuple):
            if type(valor) is str and valor in regla:
                limpio[clave] = valor
    return limpio or None


def _num(valor: Any) -> Optional[float]:
    """Número finito no negativo o None (para sumar sin que un bool, un texto o un negativo cuelen)."""
    return valor if _numero_valido(valor) else None


# ==================== AYUDAS DE PETICIÓN ====================

def _id_valido(valor: str) -> str:
    valor = (valor or "").strip()
    if not _RE_ID.match(valor):
        raise _NoDisponible("id_invalido")
    return valor


def _token(valor: str) -> str:
    valor = (valor or "").strip()
    if not valor or any(c in valor for c in "\r\n"):
        raise _NoDisponible("token_vacio")
    return valor


async def _pedir(client: httpx.AsyncClient, metodo: str, url: str, **kwargs: Any) -> Any:
    """Una petición; solo 200 con JSON de hasta 1 MB vale. Redirecciones, errores, cuerpos enormes o raros
    → _NoDisponible. El cuerpo se lee por trozos y se corta al pasar el tope (también ya descomprimido)."""
    async with client.stream(metodo, url, **kwargs) as resp:
        if resp.status_code != 200:
            raise _NoDisponible(_motivo_http(resp.status_code))
        declarado = resp.headers.get("content-length", "")
        if declarado.isdigit() and int(declarado) > MAX_CUERPO:
            raise _NoDisponible("cuerpo_grande")
        cuerpo = bytearray()
        async for trozo in resp.aiter_bytes():
            cuerpo += trozo
            if len(cuerpo) > MAX_CUERPO:
                raise _NoDisponible("cuerpo_grande")
    try:
        return json.loads(bytes(cuerpo))
    except ValueError:
        raise _NoDisponible("json_invalido")


def _inicio_de_mes(hoy: date) -> date:
    return hoy.replace(day=1)


def _fin_de_mes(hoy: date) -> date:
    return hoy.replace(day=calendar.monthrange(hoy.year, hoy.month)[1])


# ==================== CLIENTES (uno por plataforma) ====================
# Cada uno devuelve un dict «crudo» con claves de la lista blanca (que `filtrar` vuelve a comprobar).

_CONSULTA_RAILWAY = (
    "query($p: String!) { estimatedUsage(projectId: $p, measurements: [CPU_USAGE, MEMORY_USAGE_GB]) "
    "{ measurement estimatedValue } }"
)


_CONSULTA_RAILWAY_COSTO = (
    "query($p: String!) { project(id: $p) { workspace { customer { currentUsage creditBalance "
    "billingPeriod { start end } } } } }"
)


def _fin_periodo_railway(periodo: Any) -> Optional[str]:
    """Fecha (YYYY-MM-DD, UTC) del fin del período de facturación, o None si falta o no es válida."""
    fin = periodo.get("end") if isinstance(periodo, dict) else None
    if not isinstance(fin, str) or not re.match(r"^\d{4}-\d{2}-\d{2}T", fin):
        return None
    try:
        return date.fromisoformat(fin[:10]).isoformat()
    except ValueError:
        return None


def _uso_railway(datos: Any) -> dict:
    """CPU y memoria (estimatedUsage) → claves de la lista blanca."""
    if not isinstance(datos, dict):
        raise _NoDisponible("forma_inesperada")
    if datos.get("errors"):
        raise _NoDisponible("graphql_errors")
    filas = (datos.get("data") or {}).get("estimatedUsage")
    if not isinstance(filas, list):
        raise _NoDisponible("forma_inesperada")
    crudo: dict[str, Any] = {}
    for fila in filas:
        if not isinstance(fila, dict):
            continue
        valor = _num(fila.get("estimatedValue"))
        if valor is None:
            continue
        # Railway mide CPU y memoria en unidad-minuto: se convierte a unidad-hora
        if fila.get("measurement") == "CPU_USAGE":
            crudo["uso_cpu_vcpu_horas"] = valor / 60
        elif fila.get("measurement") == "MEMORY_USAGE_GB":
            crudo["uso_memoria_gb_horas"] = valor / 60
    return crudo


def _costo_railway(datos: Any) -> dict:
    """Gasto del período en US$ (currentUsage), créditos prepagados y fin del período de facturación."""
    if not isinstance(datos, dict):
        raise _NoDisponible("forma_inesperada")
    if datos.get("errors"):
        raise _NoDisponible("graphql_errors")
    cliente = ((((datos.get("data") or {}).get("project") or {}).get("workspace") or {}).get("customer"))
    if not isinstance(cliente, dict):
        raise _NoDisponible("forma_inesperada")
    crudo: dict[str, Any] = {}
    gasto = _num(cliente.get("currentUsage"))
    if gasto is not None:
        crudo["costo_estimado_mes"] = gasto
        crudo["moneda"] = "USD"
    creditos = _num(cliente.get("creditBalance"))
    if creditos is not None:
        crudo["creditos_saldo"] = creditos
    fin = _fin_periodo_railway(cliente.get("billingPeriod"))
    if fin and crudo:
        crudo["periodo_hasta"] = fin
    return crudo


async def _railway(client: httpx.AsyncClient) -> dict:
    token = _token(settings.MONITOR_RAILWAY_TOKEN)
    proyecto = _id_valido(settings.MONITOR_RAILWAY_PROJECT_ID)
    cabeceras = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # Dos consultas de solo lectura en paralelo (misma URL fija y mismo token): que una falle no tumba a la otra
    uso, costo = await asyncio.gather(
        _pedir(client, "POST", URL_RAILWAY, headers=cabeceras,
               json={"query": _CONSULTA_RAILWAY, "variables": {"p": proyecto}}),
        _pedir(client, "POST", URL_RAILWAY, headers=cabeceras,
               json={"query": _CONSULTA_RAILWAY_COSTO, "variables": {"p": proyecto}}),
        return_exceptions=True,
    )
    crudo: dict[str, Any] = {}
    ok = 0
    errores: list[BaseException] = []
    for resultado, procesar in ((uso, _uso_railway), (costo, _costo_railway)):
        try:
            if isinstance(resultado, BaseException):
                raise resultado
            crudo.update(procesar(resultado))
            ok += 1
        except Exception as e:
            errores.append(e)   # CancelledError (BaseException) sí se propaga
    if ok == 0:   # ambas fallaron: se propaga el motivo (lista cerrada) de la primera que lo tenga
        _propagar_motivo(*errores)
        raise _NoDisponible()
    if crudo and "periodo_hasta" not in crudo:
        crudo["periodo_hasta"] = _fin_de_mes(_hoy()).isoformat()
    return crudo


def _suma_decimal(resultados: list, clave: str) -> Optional[Decimal]:
    total, visto = Decimal(0), False
    for r in resultados:
        v = r.get(clave) if isinstance(r, dict) else None
        if isinstance(v, bool) or v is None:
            continue
        try:
            d = Decimal(str(v))
        except InvalidOperation:
            continue
        if d.is_finite() and d >= 0:
            total += d
            visto = True
    return total if visto else None


def _resultados(datos: Any) -> list:
    """Aplana data[].results[] de los informes de la API de administración de Anthropic."""
    if not isinstance(datos, dict) or not isinstance(datos.get("data"), list):
        raise _NoDisponible("forma_inesperada")
    salida: list = []
    for cubo in datos["data"]:
        if isinstance(cubo, dict) and isinstance(cubo.get("results"), list):
            salida.extend(cubo["results"])
    return salida


async def _anthropic(client: httpx.AsyncClient) -> dict:
    clave = _token(settings.MONITOR_ANTHROPIC_ADMIN_KEY)
    if not clave.startswith(_PREFIJO_ADMIN_ANTHROPIC):   # solo claves de administración de una organización
        raise _NoDisponible("config_invalida")
    hoy = _hoy()
    parametros = {"starting_at": f"{_inicio_de_mes(hoy).isoformat()}T00:00:00Z", "bucket_width": "1d", "limit": 31}
    cabeceras = {"x-api-key": clave, "anthropic-version": "2023-06-01"}
    uso, costo = await asyncio.gather(
        _pedir(client, "GET", URL_ANTHROPIC_USO, headers=cabeceras, params=parametros),
        _pedir(client, "GET", URL_ANTHROPIC_COSTO, headers=cabeceras, params=parametros),
        return_exceptions=True,
    )
    crudo: dict[str, Any] = {}
    # Cada informe se procesa por separado: que uno falle o venga raro no tumba al otro
    if not isinstance(uso, BaseException):
        try:
            crudo.update(_tokens_anthropic(_resultados(uso)))
        except Exception:
            pass
    if not isinstance(costo, BaseException):
        try:
            crudo.update(_costo_anthropic(_resultados(costo)))
        except Exception:
            pass
    if not crudo:
        _propagar_motivo(uso, costo)
    return crudo


def _propagar_motivo(*resultados: Any) -> None:
    """Si todo quedó vacío y alguna petición falló con motivo, ese motivo llega al log."""
    for r in resultados:
        if isinstance(r, _NoDisponible) and r.motivo:
            raise _NoDisponible(r.motivo)


def _tokens_anthropic(filas: list) -> dict:
    """Tokens del mes; un campo sin ninguna fila válida se OMITE (nunca un 0 que parezca dato real)."""
    entrada, visto = Decimal(0), False
    for campo in ("uncached_input_tokens", "cache_read_input_tokens"):
        parcial = _suma_decimal(filas, campo)
        if parcial is not None:
            entrada += parcial
            visto = True
    for r in filas:   # la escritura de caché viene anidada
        creacion = r.get("cache_creation") if isinstance(r, dict) else None
        if isinstance(creacion, dict):
            for k in creacion:
                parcial = _suma_decimal([creacion], k)
                if parcial is not None:
                    entrada += parcial
                    visto = True
    salida = _suma_decimal(filas, "output_tokens")
    crudo: dict[str, Any] = {}
    if visto:
        crudo["tokens_entrada_mes"] = int(entrada)
    if salida is not None:
        crudo["tokens_salida_mes"] = int(salida)
    return crudo


def _costo_anthropic(filas: list) -> dict:
    centavos = _suma_decimal(filas, "amount")   # «amount»: centavos como cadena decimal
    monedas = {r.get("currency") for r in filas if isinstance(r, dict)}
    if centavos is not None and monedas <= {"USD"}:
        return {"costo_mes": float(centavos / 100), "moneda": "USD"}
    return {}


async def _meta(client: httpx.AsyncClient) -> dict:
    token = _token(settings.MONITOR_META_TOKEN)
    waba = _id_valido(settings.MONITOR_META_WABA_ID)
    version = (settings.WHATSAPP_GRAPH_VERSION or "").strip()
    if not _RE_VERSION_GRAPH.match(version):
        raise _NoDisponible("config_invalida")
    hoy = _hoy()
    inicio = datetime(hoy.year, hoy.month, 1, tzinfo=timezone.utc)
    fin = datetime.now(timezone.utc)
    # `conversation_analytics` ya no existe en la API de Meta; se usa `pricing_analytics` (sin `.dimensions`).
    campos = (f"pricing_analytics.start({int(inicio.timestamp())}).end({int(fin.timestamp())})"
              ".granularity(DAILY)")
    datos = await _pedir(
        client, "GET", URL_META.format(version=version, waba=waba),
        headers={"Authorization": f"Bearer {token}"}, params={"fields": campos},
    )
    if not isinstance(datos, dict):
        raise _NoDisponible("forma_inesperada")
    analitica = datos.get("pricing_analytics")
    total = 0
    if analitica is not None:
        # Con datos: pricing_analytics.data[].data_points[].volume. Sin `pricing_analytics`: 0 facturables.
        bloques = analitica.get("data") if isinstance(analitica, dict) else None
        if not isinstance(bloques, list):
            raise _NoDisponible("forma_inesperada")
        for bloque in bloques:
            for punto in (bloque.get("data_points") if isinstance(bloque, dict) else None) or []:
                valor = _num(punto.get("volume")) if isinstance(punto, dict) else None
                if valor is not None:
                    total += valor
    return {"conversaciones_periodo": total, "periodo_desde": inicio.date().isoformat(), "periodo_hasta": hoy.isoformat()}


async def _supabase(_client: httpx.AsyncClient) -> dict:
    """Pendiente (CHG-017, ADR-008): la Management API de Supabase no ofrece un GET de solo lectura con el
    tamaño de la BD (solo `database/query`, que ejecuta SQL con un token de cuenta completa; no se usa por
    seguridad, INV-033). Hasta confirmarlo con el Dueño, la plataforma queda «no disponible»."""
    _token(settings.MONITOR_SUPABASE_TOKEN)
    raise _NoDisponible("config_invalida")


_PLANES_VERCEL = {"hobby": "gratuito", "pro": "pro"}


async def _vercel(client: httpx.AsyncClient) -> dict:
    token = _token(settings.MONITOR_VERCEL_TOKEN)
    equipo = _id_valido(settings.MONITOR_VERCEL_TEAM_ID)
    datos = await _pedir(client, "GET", URL_VERCEL_EQUIPO.format(team=equipo),
                         headers={"Authorization": f"Bearer {token}"})
    plan = ((datos.get("billing") or {}).get("plan") if isinstance(datos, dict) else None)
    if not isinstance(plan, str):
        raise _NoDisponible("forma_inesperada")
    return {"plan": _PLANES_VERCEL.get(plan.lower(), "otro")}


async def _brevo(client: httpx.AsyncClient) -> dict:
    clave = _token(settings.MONITOR_BREVO_KEY)
    cabeceras = {"api-key": clave, "accept": "application/json"}
    hoy = _hoy().isoformat()
    cuenta, reporte = await asyncio.gather(
        _pedir(client, "GET", URL_BREVO_CUENTA, headers=cabeceras),
        _pedir(client, "GET", URL_BREVO_REPORTE, headers=cabeceras, params={"startDate": hoy, "endDate": hoy}),
        return_exceptions=True,
    )
    crudo: dict[str, Any] = {}
    if not isinstance(cuenta, BaseException) and isinstance(cuenta, dict):
        creditos, visto = 0, False
        for plan in cuenta.get("plan") or []:
            if isinstance(plan, dict) and plan.get("creditsType") == "sendLimit":
                valor = _num(plan.get("credits"))
                if valor is not None:
                    creditos += valor
                    visto = True
        if visto:
            crudo["creditos_restantes"] = creditos
    if not isinstance(reporte, BaseException) and isinstance(reporte, dict):
        enviados = _num(reporte.get("requests"))
        if enviados is not None:
            crudo["enviados_hoy"] = enviados
    if not crudo:
        _propagar_motivo(cuenta, reporte)
    return crudo


_CLIENTES: dict[str, Callable[[httpx.AsyncClient], Awaitable[dict]]] = {
    "railway": _railway, "anthropic": _anthropic, "meta": _meta,
    "supabase": _supabase, "vercel": _vercel, "brevo": _brevo,
}


# ==================== CONSULTA, CACHÉ Y PARALELISMO ====================

async def _ejecutar(nombre: str) -> Optional[dict]:
    # Sin seguir redirecciones (INV-034); el plazo total lo impone `asyncio.wait_for` en `_consultar`
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_TOTAL), follow_redirects=False) as client:
        crudo = await _CLIENTES[nombre](client)
    datos = filtrar(nombre, crudo)
    if datos is None:
        raise _NoDisponible("sin_campos")
    return datos


async def _consultar(nombre: str) -> dict:
    """Consulta una plataforma con caché. Nunca lanza: cualquier fallo → no_disponible (INV-032)."""
    ahora = _reloj()
    guardado = _cache.get(nombre)
    if guardado and guardado[0] > ahora:
        return guardado[1]
    try:
        datos = await asyncio.wait_for(_ejecutar(nombre), timeout=TIMEOUT_TOTAL)
    except Exception as e:   # incluye TimeoutError; CancelledError sí se propaga
        # Solo el nombre, el TIPO del error y, si lo hay, un motivo de lista cerrada: nunca el mensaje,
        # la URL, las cabeceras, el cuerpo ni el token
        motivo = getattr(e, "motivo", None) if isinstance(e, _NoDisponible) else None
        detalle = f"{type(e).__name__}: {motivo}" if motivo else type(e).__name__
        print(f"[monitor] {nombre}: no disponible ({detalle})")
        datos = None
    if datos:
        resultado = {"estado": "ok", "datos": datos, "actualizado_en": _iso_utc()}
        vigencia = CACHE_OK
    else:
        resultado = _no_disponible()
        vigencia = CACHE_FALLO
    _cache[nombre] = (_reloj() + vigencia, resultado)
    return resultado


async def consultar_todas() -> dict[str, dict]:
    """Las seis plataformas en paralelo: {nombre: {estado, datos, actualizado_en}}. Nunca lanza."""
    resultados = await asyncio.gather(*(_consultar(n) for n in PLATAFORMAS), return_exceptions=True)
    return {n: (r if isinstance(r, dict) else _no_disponible()) for n, r in zip(PLATAFORMAS, resultados)}


def limpiar_cache() -> None:
    _cache.clear()
