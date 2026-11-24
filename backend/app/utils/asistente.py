"""
Asistente financiero con Claude (CHG-010, CT-007, ADR-006).

Cómo funciona (tool use):
1. El usuario hace una pregunta en lenguaje natural ("¿cuáles fueron mis gastos más altos del mes?").
2. Se envía a la API de Claude junto con la lista de HERRAMIENTAS de solo lectura de abajo.
3. Claude decide qué herramienta necesita (p. ej. `movimientos_principales` con mes=2026-11);
   el backend la ejecuta contra la BD y le devuelve el resultado.
4. Claude redacta la respuesta final con esos datos.

Seguridad (INV-023):
- Las herramientas SOLO leen. No existe ninguna herramienta que cree, edite o borre.
- El `usuario_id` sale SIEMPRE del token de sesión y nunca de lo que diga el modelo: Claude
  no puede pedir datos de otra persona aunque lo intente (no hay parámetro para eso).
- A Claude solo se envían los datos que pide cada herramienta, ya agregados; nunca el correo,
  la contraseña ni el id del usuario.
- La clave ANTHROPIC_API_KEY vive solo en el backend y nunca se escribe en los logs.

Costo: modelo configurable (por defecto Haiku, el más económico), respuesta corta
(`MAX_TOKENS`) y como mucho `MAX_RONDAS` llamadas por pregunta. Los topes diarios están en
la ruta (`api/routes/asistente.py`).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.models import contadores
from app.models.plataapp import CategoriaDB, MetaDB, PresupuestoDB, TransaccionDB

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MAX_TOKENS = 1024
MAX_RONDAS = 5          # llamadas a Claude por pregunta (la última se fuerza a responder sin herramientas)
TIMEOUT_SEGUNDOS = 45
MAX_MOVIMIENTOS = 20    # tope de filas que una herramienta devuelve a Claude

# Colombia no tiene horario de verano: UTC-5 fijo (sin depender de tzdata en la imagen Docker)
ZONA_COLOMBIA = timezone(timedelta(hours=-5))
_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_SIN_CATEGORIA = "Sin categoría"


class AsistenteError(Exception):
    """Error controlado del asistente: `status` y `detalle` van tal cual al cliente."""

    def __init__(self, status: int, detalle: str):
        super().__init__(detalle)
        self.status = status
        self.detalle = detalle


# ==================== HERRAMIENTAS (solo lectura) ====================

_PROP_MES = {"type": "string", "description": "Mes en formato YYYY-MM, p. ej. 2026-11"}
_PROP_TIPO = {
    "type": "string",
    "enum": ["gasto", "ingreso"],
    "description": "gasto o ingreso. Por defecto gasto.",
}

HERRAMIENTAS: list[dict] = [
    {
        "name": "resumen_mes",
        "description": "Totales de un mes: ingresos, gastos, balance y número de movimientos.",
        "input_schema": {"type": "object", "properties": {"mes": _PROP_MES}, "required": ["mes"]},
    },
    {
        "name": "movimientos_principales",
        "description": (
            "Los movimientos individuales de mayor monto de un mes (los gastos más altos o los "
            "ingresos más altos), con fecha, descripción, categoría y medio de pago."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mes": _PROP_MES,
                "tipo": _PROP_TIPO,
                "limite": {"type": "integer", "minimum": 1, "maximum": MAX_MOVIMIENTOS,
                           "description": "Cuántos devolver (1-20). Por defecto 5."},
            },
            "required": ["mes"],
        },
    },
    {
        "name": "totales_por_categoria",
        "description": (
            "Total por categoría en un mes, de mayor a menor. Para gastos incluye el presupuesto "
            "de la categoría (si tiene) y el porcentaje usado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"mes": _PROP_MES, "tipo": _PROP_TIPO},
            "required": ["mes"],
        },
    },
    {
        "name": "totales_por_medio_pago",
        "description": "Total por medio de pago (débito, crédito, efectivo, transferencia, Nequi/Daviplata) en un mes.",
        "input_schema": {
            "type": "object",
            "properties": {"mes": _PROP_MES, "tipo": _PROP_TIPO},
            "required": ["mes"],
        },
    },
    {
        "name": "buscar_movimientos",
        "description": (
            "Busca movimientos cuya descripción o categoría contenga un texto (sin distinguir "
            "mayúsculas ni tildes), p. ej. 'rappi' o 'gasolina'. Devuelve el total y hasta 20 movimientos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "texto": {"type": "string", "minLength": 2, "maxLength": 60},
                "mes": {**_PROP_MES, "description": "Opcional. Si no se envía, busca en todos los meses."},
            },
            "required": ["texto"],
        },
    },
    {
        "name": "metas_ahorro",
        "description": "Las metas de ahorro del usuario con monto objetivo, ahorrado, porcentaje y fecha objetivo.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

_MEDIOS = {
    "debito": "Débito", "credito": "Crédito", "efectivo": "Efectivo",
    "transferencia": "Transferencia", "nequi_daviplata": "Nequi / Daviplata",
}


def _num(valor: Any) -> float:
    return round(float(valor or 0), 2)


def _sin_tildes(texto: str) -> str:
    tabla = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return (texto or "").translate(tabla).lower()


def _validar_mes(entrada: dict, requerido: bool = True) -> Optional[str]:
    mes = entrada.get("mes")
    if mes is None and not requerido:
        return None
    if not isinstance(mes, str) or not _MES.match(mes):
        raise ValueError("El mes debe tener el formato YYYY-MM")
    return mes


def _validar_tipo(entrada: dict) -> str:
    tipo = entrada.get("tipo") or "gasto"
    if tipo not in ("gasto", "ingreso"):
        raise ValueError("El tipo debe ser 'gasto' o 'ingreso'")
    return tipo


async def _nombres_categorias(usuario_id: str) -> dict[str, str]:
    categorias = await CategoriaDB.obtener_por_usuario(usuario_id)
    return {str(c["id"]): c.get("nombre") or _SIN_CATEGORIA for c in categorias}


def _fila(t: dict, nombres: dict[str, str]) -> dict:
    return {
        "fecha": t.get("fecha"),
        "monto": _num(t.get("monto")),
        "tipo": t.get("tipo"),
        "descripcion": t.get("descripcion") or "",
        "categoria": nombres.get(str(t.get("categoria_id")), _SIN_CATEGORIA),
        "medio_pago": _MEDIOS.get(t.get("medio_pago") or "", "Sin medio de pago"),
    }


async def _resumen_mes(usuario_id: str, entrada: dict) -> dict:
    mes = _validar_mes(entrada)
    resumen = await TransaccionDB.obtener_resumen(usuario_id, mes)
    return {"mes": mes, **{k: _num(v) if k != "total_transacciones" else v for k, v in resumen.items()}}


async def _movimientos_principales(usuario_id: str, entrada: dict) -> dict:
    mes, tipo = _validar_mes(entrada), _validar_tipo(entrada)
    limite = entrada.get("limite", 5)
    if type(limite) is not int or not 1 <= limite <= MAX_MOVIMIENTOS:
        limite = 5
    movimientos = [t for t in await TransaccionDB.obtener_por_usuario(usuario_id, mes) if t.get("tipo") == tipo]
    movimientos.sort(key=lambda t: float(t.get("monto") or 0), reverse=True)
    nombres = await _nombres_categorias(usuario_id)
    return {
        "mes": mes, "tipo": tipo, "total_movimientos_del_mes": len(movimientos),
        "movimientos": [_fila(t, nombres) for t in movimientos[:limite]],
    }


async def _totales_por_categoria(usuario_id: str, entrada: dict) -> dict:
    mes, tipo = _validar_mes(entrada), _validar_tipo(entrada)
    movimientos = [t for t in await TransaccionDB.obtener_por_usuario(usuario_id, mes) if t.get("tipo") == tipo]
    nombres = await _nombres_categorias(usuario_id)
    totales: dict[str, float] = defaultdict(float)
    cantidad: dict[str, int] = defaultdict(int)
    for t in movimientos:
        nombre = nombres.get(str(t.get("categoria_id")), _SIN_CATEGORIA)
        totales[nombre] += float(t.get("monto") or 0)
        cantidad[nombre] += 1
    limites: dict[str, float] = {}
    if tipo == "gasto":
        for p in await PresupuestoDB.obtener_por_usuario_mes(usuario_id, mes):
            nombre = nombres.get(str(p.get("categoria_id")))
            if nombre:
                limites[nombre] = limites.get(nombre, 0) + float(p.get("limite_mensual") or 0)
    filas = []
    for nombre in sorted(set(totales) | set(limites), key=lambda n: totales.get(n, 0), reverse=True):
        fila: dict[str, Any] = {"categoria": nombre, "total": _num(totales.get(nombre)), "movimientos": cantidad.get(nombre, 0)}
        if nombre in limites:
            fila["presupuesto"] = _num(limites[nombre])
            fila["porcentaje_usado"] = round(totales.get(nombre, 0) / limites[nombre] * 100, 1) if limites[nombre] else None
        filas.append(fila)
    return {"mes": mes, "tipo": tipo, "total": _num(sum(totales.values())), "categorias": filas}


async def _totales_por_medio_pago(usuario_id: str, entrada: dict) -> dict:
    mes, tipo = _validar_mes(entrada), _validar_tipo(entrada)
    totales: dict[str, float] = defaultdict(float)
    for t in await TransaccionDB.obtener_por_usuario(usuario_id, mes):
        if t.get("tipo") == tipo:
            totales[_MEDIOS.get(t.get("medio_pago") or "", "Sin medio de pago")] += float(t.get("monto") or 0)
    filas = [{"medio_pago": m, "total": _num(v)} for m, v in sorted(totales.items(), key=lambda x: x[1], reverse=True)]
    return {"mes": mes, "tipo": tipo, "medios": filas}


async def _buscar_movimientos(usuario_id: str, entrada: dict) -> dict:
    texto = entrada.get("texto")
    if not isinstance(texto, str) or not 2 <= len(texto.strip()) <= 60:
        raise ValueError("El texto de búsqueda debe tener entre 2 y 60 caracteres")
    mes = _validar_mes(entrada, requerido=False)
    buscado = _sin_tildes(texto.strip())
    nombres = await _nombres_categorias(usuario_id)
    encontrados = [
        t for t in await TransaccionDB.obtener_por_usuario(usuario_id, mes)
        if buscado in _sin_tildes(t.get("descripcion") or "")
        or buscado in _sin_tildes(nombres.get(str(t.get("categoria_id")), ""))
    ]
    encontrados.sort(key=lambda t: str(t.get("fecha") or ""), reverse=True)
    return {
        "texto": texto, "mes": mes or "todos",
        "cantidad": len(encontrados),
        "total_gastos": _num(sum(float(t["monto"]) for t in encontrados if t.get("tipo") == "gasto")),
        "total_ingresos": _num(sum(float(t["monto"]) for t in encontrados if t.get("tipo") == "ingreso")),
        "movimientos": [_fila(t, nombres) for t in encontrados[:MAX_MOVIMIENTOS]],
    }


async def _metas_ahorro(usuario_id: str, _entrada: dict) -> dict:
    metas = []
    for m in await MetaDB.obtener_por_usuario(usuario_id):
        objetivo, actual = float(m.get("monto_objetivo") or 0), float(m.get("monto_actual") or 0)
        metas.append({
            "nombre": m.get("nombre"), "monto_objetivo": _num(objetivo), "monto_ahorrado": _num(actual),
            "porcentaje": round(actual / objetivo * 100, 1) if objetivo > 0 else 0,
            "fecha_objetivo": m.get("fecha_objetivo"),
        })
    return {"metas": metas}


_EJECUTORES = {
    "resumen_mes": _resumen_mes,
    "movimientos_principales": _movimientos_principales,
    "totales_por_categoria": _totales_por_categoria,
    "totales_por_medio_pago": _totales_por_medio_pago,
    "buscar_movimientos": _buscar_movimientos,
    "metas_ahorro": _metas_ahorro,
}


async def ejecutar_herramienta(usuario_id: str, nombre: str, entrada: Any) -> tuple[str, bool]:
    """Ejecuta una herramienta para el usuario del TOKEN. Devuelve (json, es_error)."""
    ejecutor = _EJECUTORES.get(nombre)
    if ejecutor is None:
        return json.dumps({"error": f"Herramienta desconocida: {nombre}"}, ensure_ascii=False), True
    try:
        resultado = await ejecutor(usuario_id, entrada if isinstance(entrada, dict) else {})
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False), True
    return json.dumps(resultado, ensure_ascii=False, default=str), False


# ==================== CONVERSACIÓN CON CLAUDE ====================

def _prompt_sistema(ahora: datetime) -> str:
    mes_actual = ahora.strftime("%Y-%m")
    primero = ahora.replace(day=1)
    mes_anterior = (primero - timedelta(days=1)).strftime("%Y-%m")
    return (
        "Eres el asistente financiero de Finanzy, una app personal de finanzas. Respondes en español, "
        "de forma breve, clara y amable, sobre los ingresos, gastos, presupuestos y metas del usuario.\n"
        f"- Hoy es {ahora.strftime('%Y-%m-%d')} (hora de Colombia). 'Este mes' es {mes_actual} y "
        f"'el mes pasado' es {mes_anterior}.\n"
        "- Usa SIEMPRE las herramientas para obtener los datos; nunca inventes cifras. Si una herramienta "
        "no devuelve datos, dilo con naturalidad.\n"
        "- Los montos están en pesos colombianos (COP). Escríbelos así: $1.250.000 (punto de miles, sin decimales "
        "salvo que importen).\n"
        "- Formato: texto plano con viñetas '- ' si hay varios elementos. No uses tablas, títulos con # ni negritas.\n"
        "- Solo puedes CONSULTAR. Si te piden registrar, editar o borrar algo, explica que eso se hace en la app.\n"
        "- Si la pregunta no tiene que ver con las finanzas del usuario, indícalo en una frase y ofrece ayuda con "
        "sus finanzas. No des asesoría de inversión personalizada."
    )


def _mensajes(historial: list[dict], pregunta: str) -> list[dict]:
    """Convierte el historial a mensajes de la API: empieza por el usuario y alterna roles
    (si llegan dos seguidos del mismo rol, se unen)."""
    mensajes: list[dict] = []
    for item in [*historial, {"rol": "usuario", "texto": pregunta}]:
        rol = "user" if item["rol"] == "usuario" else "assistant"
        if not mensajes and rol == "assistant":
            continue
        if mensajes and mensajes[-1]["role"] == rol:
            mensajes[-1]["content"] += "\n\n" + item["texto"]
        else:
            mensajes.append({"role": rol, "content": item["texto"]})
    return mensajes


async def _contar_uso(origen: str, datos: Any) -> None:
    """Cuenta la llamada y sus tokens (CHG-017, INV-036). Nunca lanza ni rompe la respuesta."""
    try:
        uso = datos.get("usage") if isinstance(datos, dict) else None
        uso = uso if isinstance(uso, dict) else {}
        await contadores.incrementar_async("claude_llamadas", origen, 1)
        for metrica, clave in (("claude_tokens_entrada", "input_tokens"), ("claude_tokens_salida", "output_tokens")):
            valor = uso.get(clave)
            if type(valor) is int and valor > 0:
                await contadores.incrementar_async(metrica, origen, valor)
    except Exception as e:
        print(f"[asistente] Aviso: no se pudo contar el uso ({type(e).__name__})")


async def llamar_claude(payload: dict, origen: str = "asistente") -> dict:
    """Una llamada a la API de mensajes de Claude. Se reemplaza en las pruebas.

    `origen` (asistente | whatsapp) solo sirve para los contadores del Monitor."""
    headers = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as client:
            resp = await client.post(API_URL, headers=headers, json=payload)
    except httpx.HTTPError as e:
        print(f"[asistente] Sin conexión con la API de Claude ({type(e).__name__})")
        raise AsistenteError(503, "El asistente no está disponible en este momento. Intenta de nuevo.")
    if resp.status_code == 200:
        datos = resp.json()
        await _contar_uso(origen, datos)
        return datos
    # Nunca se registra la clave ni el cuerpo enviado; solo el estado y el tipo de error
    try:
        tipo = resp.json().get("error", {}).get("type", "")
    except ValueError:
        tipo = ""
    print(f"[asistente] La API de Claude respondió {resp.status_code} {tipo}")
    if resp.status_code in (401, 403):
        raise AsistenteError(503, "El asistente no está configurado correctamente.")
    if resp.status_code == 400 and "credit" in resp.text.lower():
        raise AsistenteError(503, "El asistente no tiene saldo disponible en este momento.")
    if resp.status_code in (429, 529) or resp.status_code >= 500:
        raise AsistenteError(503, "El asistente está ocupado. Intenta de nuevo en unos segundos.")
    raise AsistenteError(502, "El asistente no pudo responder. Intenta de nuevo.")


async def responder(usuario_id: str, pregunta: str, historial: list[dict]) -> dict:
    """Ciclo de tool use: pregunta → herramientas → respuesta final."""
    mensajes = _mensajes(historial, pregunta)
    sistema = _prompt_sistema(datetime.now(ZONA_COLOMBIA))
    uso = {"input_tokens": 0, "output_tokens": 0}

    for ronda in range(MAX_RONDAS):
        payload = {
            "model": settings.ANTHROPIC_MODEL,
            "max_tokens": MAX_TOKENS,
            "system": sistema,
            "tools": HERRAMIENTAS,
            "messages": mensajes,
        }
        if ronda == MAX_RONDAS - 1:
            payload["tool_choice"] = {"type": "none"}  # última ronda: responder con lo que ya tiene
        datos = await llamar_claude(payload, origen="asistente")
        for clave in uso:
            uso[clave] += int((datos.get("usage") or {}).get(clave) or 0)
        contenido = datos.get("content") or []

        if datos.get("stop_reason") != "tool_use":
            texto = "\n".join(b.get("text", "") for b in contenido if b.get("type") == "text").strip()
            return {
                "respuesta": texto or "No encontré una respuesta. ¿Puedes reformular la pregunta?",
                "modelo": datos.get("model") or settings.ANTHROPIC_MODEL,
                "uso": uso,
            }

        resultados = []
        for bloque in contenido:
            if bloque.get("type") != "tool_use":
                continue
            # usuario_id viene del token, nunca de `bloque["input"]` (INV-023)
            salida, es_error = await ejecutar_herramienta(usuario_id, bloque.get("name", ""), bloque.get("input"))
            resultado = {"type": "tool_result", "tool_use_id": bloque.get("id"), "content": salida}
            if es_error:
                resultado["is_error"] = True
            resultados.append(resultado)
        mensajes = [*mensajes, {"role": "assistant", "content": contenido}, {"role": "user", "content": resultados}]

    raise AsistenteError(502, "El asistente no pudo completar la respuesta. Intenta con una pregunta más concreta.")
