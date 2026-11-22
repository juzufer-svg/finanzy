"""CHG-010 · INV-023 / INV-024: asistente con Claude (CT-007).

La API de Claude nunca se llama de verdad: `llamar_claude` se reemplaza por un guion de
respuestas, y se revisa lo que el backend le habría enviado.
"""
import json

import pytest

from app.api.routes import asistente as rutas
from app.core.config import settings
from app.utils import asistente
from conftest import auth_header

A = auth_header("user-a")
B = auth_header("user-b")
URL = "/api/v1/asistente/chat"


@pytest.fixture
def claude(monkeypatch):
    """Simula la API de Claude: devuelve las respuestas de `guion` en orden y guarda los payloads."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-prueba")
    estado = {"guion": [], "payloads": []}

    async def falsa(payload):
        estado["payloads"].append(json.loads(json.dumps(payload)))
        return estado["guion"].pop(0)

    monkeypatch.setattr(asistente, "llamar_claude", falsa)
    return estado


def usa(nombre, entrada, id_="tu_1"):
    return {"stop_reason": "tool_use", "usage": {"input_tokens": 100, "output_tokens": 20},
            "content": [{"type": "tool_use", "id": id_, "name": nombre, "input": entrada}]}


def texto(t):
    return {"stop_reason": "end_turn", "model": "claude-haiku-5-5",
            "usage": {"input_tokens": 150, "output_tokens": 40}, "content": [{"type": "text", "text": t}]}


def _tx(client, headers, monto, descripcion, tipo="gasto", fecha="2026-11-10", **extra):
    body = {"categoria_id": "", "monto": monto, "descripcion": descripcion, "fecha": fecha, "tipo": tipo, **extra}
    assert client.post("/api/v1/transacciones", json=body, headers=headers).status_code == 200


def _resultado_herramienta(payload):
    """Contenido (dict) y bandera de error del tool_result que el backend devolvió a Claude."""
    bloque = payload["messages"][-1]["content"][0]
    assert bloque["type"] == "tool_result"
    return json.loads(bloque["content"]), bloque.get("is_error", False)


# ---------- Configuración y validación ----------

def test_sin_clave_responde_503_y_no_llama_a_claude(client, monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    llamado = []

    async def falsa(payload):
        llamado.append(payload)

    monkeypatch.setattr(asistente, "llamar_claude", falsa)
    r = client.post(URL, json={"pregunta": "hola"}, headers=A)
    assert r.status_code == 503 and llamado == []


def test_exige_sesion(client, claude):
    assert client.post(URL, json={"pregunta": "hola"}, headers={"Authorization": "Bearer malo"}).status_code == 401
    assert claude["payloads"] == []


@pytest.mark.parametrize("body", [
    {"pregunta": ""},
    {"pregunta": "x" * 501},
    {"pregunta": "hola", "historial": [{"rol": "usuario", "texto": "a"}] * 11},
    {"pregunta": "hola", "historial": [{"rol": "sistema", "texto": "a"}]},
])
def test_valida_la_entrada(client, claude, body):
    assert client.post(URL, json=body, headers=A).status_code == 422
    assert claude["payloads"] == []


# ---------- Flujo con herramientas ----------

def test_gastos_mas_altos_del_mes_con_herramienta(client, claude):
    _tx(client, A, 50_000, "Mercado", medio_pago="debito")
    _tx(client, A, 900_000, "Arriendo", medio_pago="transferencia")
    _tx(client, A, 3_000_000, "Salario", tipo="ingreso")
    _tx(client, A, 70_000, "Mes pasado", fecha="2026-10-30")
    claude["guion"] = [usa("movimientos_principales", {"mes": "2026-11", "limite": 2}), texto("Tu gasto más alto fue Arriendo.")]

    r = client.post(URL, json={"pregunta": "¿Cuáles fueron mis gastos más altos del mes?"}, headers=A)

    assert r.status_code == 200
    assert r.json() == {"respuesta": "Tu gasto más alto fue Arriendo.", "modelo": "claude-haiku-5-5",
                        "uso": {"input_tokens": 250, "output_tokens": 60}}
    datos, es_error = _resultado_herramienta(claude["payloads"][1])
    assert not es_error
    assert [m["descripcion"] for m in datos["movimientos"]] == ["Arriendo", "Mercado"]
    assert datos["movimientos"][0]["medio_pago"] == "Transferencia"
    # Solo herramientas de lectura y el modelo configurado
    assert claude["payloads"][0]["model"] == settings.ANTHROPIC_MODEL
    assert {h["name"] for h in claude["payloads"][0]["tools"]} == set(asistente._EJECUTORES)


def test_inv023_solo_ve_los_datos_del_usuario_del_token(client, claude):
    _tx(client, A, 10_000, "Gasto de A")
    _tx(client, B, 999_999, "Gasto secreto de B")
    # Aunque el modelo intente pedir datos de otro usuario, el parámetro se ignora
    claude["guion"] = [usa("movimientos_principales", {"mes": "2026-11", "usuario_id": "user-b"}), texto("ok")]
    assert client.post(URL, json={"pregunta": "gastos"}, headers=A).status_code == 200
    datos, _ = _resultado_herramienta(claude["payloads"][1])
    assert [m["descripcion"] for m in datos["movimientos"]] == ["Gasto de A"]
    # Lo que el backend envía a Claude (sistema y resultados) no incluye datos de B ni ids de usuario
    resultados = json.dumps(claude["payloads"][1]["messages"][-1], ensure_ascii=False)
    assert "secreto" not in resultados and "user-" not in resultados
    assert "user-" not in claude["payloads"][0]["system"]


def test_inv023_las_herramientas_no_cambian_datos(client, claude):
    _tx(client, A, 10_000, "Taxi")
    antes = client.get("/api/v1/transacciones", headers=A).json()
    # Claude puede pedir varias herramientas en una misma respuesta: aquí, todas
    bloques = [usa(n, {"mes": "2026-11", "texto": "taxi"}, f"t{i}")["content"][0] for i, n in enumerate(asistente._EJECUTORES)]
    claude["guion"] = [{"stop_reason": "tool_use", "content": bloques}, texto("listo")]
    assert client.post(URL, json={"pregunta": "todo"}, headers=A).status_code == 200
    assert client.get("/api/v1/transacciones", headers=A).json() == antes
    resultados = claude["payloads"][1]["messages"][-1]["content"]
    assert len(resultados) == len(asistente._EJECUTORES) and not any(r.get("is_error") for r in resultados)


@pytest.mark.parametrize("nombre,entrada", [
    ("borrar_todo", {}),
    ("resumen_mes", {"mes": "noviembre"}),
    ("buscar_movimientos", {"texto": "x"}),
])
def test_herramienta_invalida_devuelve_error_a_claude_sin_romper(client, claude, nombre, entrada):
    claude["guion"] = [usa(nombre, entrada), texto("No pude consultar eso.")]
    r = client.post(URL, json={"pregunta": "algo"}, headers=A)
    assert r.status_code == 200
    datos, es_error = _resultado_herramienta(claude["payloads"][1])
    assert es_error and "error" in datos


def test_totales_por_categoria_con_presupuesto(client, claude):
    cats = client.get("/api/v1/categorias", headers=A).json()
    comida = next(c for c in cats if c["nombre"] == "Comida")
    _tx(client, A, 300_000, "Restaurante", categoria_id=comida["id"])
    _tx(client, A, 100_000, "Sin cat")
    client.post("/api/v1/presupuestos", json={"categoria_id": comida["id"], "limite_mensual": 400_000, "mes_ano": "2026-11"}, headers=A)
    claude["guion"] = [usa("totales_por_categoria", {"mes": "2026-11"}), texto("ok")]
    client.post(URL, json={"pregunta": "por categoría"}, headers=A)
    datos, _ = _resultado_herramienta(claude["payloads"][1])
    assert datos["total"] == 400_000
    assert datos["categorias"][0] == {"categoria": "Comida", "total": 300_000, "movimientos": 1,
                                      "presupuesto": 400_000, "porcentaje_usado": 75.0}
    assert datos["categorias"][1]["categoria"] == "Sin categoría"


def test_buscar_ignora_mayusculas_y_tildes(client, claude):
    _tx(client, A, 20_000, "Café en la oficina")
    _tx(client, A, 5_000, "Bus")
    claude["guion"] = [usa("buscar_movimientos", {"texto": "CAFE"}), texto("ok")]
    client.post(URL, json={"pregunta": "café"}, headers=A)
    datos, _ = _resultado_herramienta(claude["payloads"][1])
    assert datos["cantidad"] == 1 and datos["total_gastos"] == 20_000


def test_ultima_ronda_obliga_a_responder_sin_herramientas(client, claude):
    claude["guion"] = [usa("metas_ahorro", {}, f"t{i}") for i in range(asistente.MAX_RONDAS - 1)] + [texto("fin")]
    r = client.post(URL, json={"pregunta": "metas"}, headers=A)
    assert r.status_code == 200 and r.json()["respuesta"] == "fin"
    assert len(claude["payloads"]) == asistente.MAX_RONDAS
    assert claude["payloads"][-1]["tool_choice"] == {"type": "none"}
    assert "tool_choice" not in claude["payloads"][0]


def test_historial_se_normaliza(client, claude):
    claude["guion"] = [texto("ok")]
    historial = [
        {"rol": "asistente", "texto": "saludo suelto"},  # no puede empezar el asistente: se descarta
        {"rol": "usuario", "texto": "¿gastos de noviembre?"},
        {"rol": "asistente", "texto": "Fueron $100.000"},
        {"rol": "usuario", "texto": "pregunta sin respuesta"},
    ]
    client.post(URL, json={"pregunta": "¿y octubre?", "historial": historial}, headers=A)
    mensajes = claude["payloads"][0]["messages"]
    assert [m["role"] for m in mensajes] == ["user", "assistant", "user"]
    assert mensajes[-1]["content"] == "pregunta sin respuesta\n\n¿y octubre?"


def test_error_de_la_api_se_traduce(client, claude, monkeypatch):
    async def falla(payload):
        raise asistente.AsistenteError(503, "El asistente está ocupado. Intenta de nuevo en unos segundos.")

    monkeypatch.setattr(asistente, "llamar_claude", falla)
    r = client.post(URL, json={"pregunta": "hola"}, headers=A)
    assert r.status_code == 503 and "ocupado" in r.json()["detail"]


# ---------- Topes de costo (INV-024) ----------

def test_inv024_limite_diario_por_usuario(client, claude, monkeypatch):
    monkeypatch.setattr(rutas._por_usuario_dia, "limit", 2)
    claude["guion"] = [texto("ok")] * 3
    assert client.post(URL, json={"pregunta": "1"}, headers=A).status_code == 200
    assert client.post(URL, json={"pregunta": "2"}, headers=A).status_code == 200
    r = client.post(URL, json={"pregunta": "3"}, headers=A)
    assert r.status_code == 429 and len(claude["payloads"]) == 2
    # Otro usuario no se ve afectado
    assert client.post(URL, json={"pregunta": "1"}, headers=B).status_code == 200


def test_inv024_limite_por_minuto(client, claude):
    claude["guion"] = [texto("ok")] * 6
    codigos = [client.post(URL, json={"pregunta": str(i)}, headers=A).status_code for i in range(6)]
    assert codigos == [200] * 5 + [429]


def test_inv024_limite_global_diario(client, claude, monkeypatch):
    monkeypatch.setattr(rutas._global_dia, "limit", 1)
    claude["guion"] = [texto("ok")] * 2
    assert client.post(URL, json={"pregunta": "1"}, headers=A).status_code == 200
    assert client.post(URL, json={"pregunta": "1"}, headers=B).status_code == 429
    assert len(claude["payloads"]) == 1


# ---------- Llamada HTTP real (con transporte simulado) ----------

@pytest.mark.parametrize("status,cuerpo,esperado", [
    (401, {"error": {"type": "authentication_error"}}, 503),
    (429, {"error": {"type": "rate_limit_error"}}, 503),
    (529, {"error": {"type": "overloaded_error"}}, 503),
    (400, {"error": {"type": "invalid_request_error", "message": "Your credit balance is too low"}}, 503),
    (400, {"error": {"type": "invalid_request_error"}}, 502),
])
def test_llamar_claude_traduce_errores_sin_filtrar_la_clave(monkeypatch, capsys, status, cuerpo, esperado):
    import asyncio
    import httpx

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-secreta-123")
    enviados = []

    def manejador(request):
        enviados.append(request)
        return httpx.Response(status, json=cuerpo)

    real = httpx.AsyncClient
    monkeypatch.setattr(asistente.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(manejador), **kw))
    with pytest.raises(asistente.AsistenteError) as e:
        asyncio.run(asistente.llamar_claude({"model": "m"}))
    assert e.value.status == esperado
    assert enviados[0].headers["x-api-key"] == "sk-ant-secreta-123"
    assert "sk-ant-secreta" not in capsys.readouterr().out
