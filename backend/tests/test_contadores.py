"""CHG-017 · REQ-F-018 · INV-036 (T1): contadores diarios del Monitor (BDD-MONITOR).

Solo agregados, nunca datos personales, y un fallo al contar jamás rompe el flujo principal.
Sin Supabase real: el modelo usa su almacén en memoria y, donde hace falta, un cliente simulado.
La prueba de RLS, clave única, incremento atómico y purga en SQL está en `sql/pruebas/06_comprobar_monitor.sql`.
"""
import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core.config import settings
from app.models import contadores, whatsapp as whatsapp_db
from app.utils import asistente, email as em, whatsapp as wa
from conftest import auth_header

_REAL_CLIENT = httpx.AsyncClient   # el original, aunque otra prueba lo reemplace
SECRETO = "secreto-de-la-app-de-meta"
TEL = "573001112233"
CORREO = "persona.privada@example.com"


def _total(metrica, origen="general"):
    return sum(c for (_f, m, o), c in contadores._Memoria.filas.items() if m == metrica and o == origen)


def _claves():
    return {(m, o) for (_f, m, o) in contadores._Memoria.filas}


# ---------- Claude ----------

def _claude_httpx(monkeypatch, cuerpo, status=200):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-prueba")
    real = _REAL_CLIENT
    monkeypatch.setattr(asistente.httpx, "AsyncClient", lambda **kw: real(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, json=cuerpo)), **kw))


@pytest.mark.parametrize("origen", ["asistente", "whatsapp"])
def test_inv036_llamar_claude_cuenta_llamada_y_tokens(monkeypatch, origen):
    _claude_httpx(monkeypatch, {"content": [], "usage": {"input_tokens": 120, "output_tokens": 30}})
    asyncio.run(asistente.llamar_claude({"model": "m"}, origen=origen))
    asyncio.run(asistente.llamar_claude({"model": "m"}, origen=origen))
    assert _total("claude_llamadas", origen) == 2
    assert _total("claude_tokens_entrada", origen) == 240
    assert _total("claude_tokens_salida", origen) == 60
    otro = "whatsapp" if origen == "asistente" else "asistente"
    assert _total("claude_llamadas", otro) == 0


def test_inv036_llamar_claude_por_defecto_es_asistente_y_no_cuenta_los_errores(monkeypatch):
    _claude_httpx(monkeypatch, {"content": [], "usage": {"input_tokens": 5, "output_tokens": 1}})
    asyncio.run(asistente.llamar_claude({"model": "m"}))
    assert _total("claude_llamadas", "asistente") == 1
    _claude_httpx(monkeypatch, {"error": {"type": "overloaded_error"}}, status=529)
    with pytest.raises(asistente.AsistenteError):
        asyncio.run(asistente.llamar_claude({"model": "m"}))
    assert _total("claude_llamadas", "asistente") == 1


def test_inv036_uso_ausente_o_raro_solo_cuenta_la_llamada(monkeypatch):
    _claude_httpx(monkeypatch, {"content": [], "usage": {"input_tokens": "x", "output_tokens": -4}})
    asyncio.run(asistente.llamar_claude({"model": "m"}))
    assert _total("claude_llamadas", "asistente") == 1
    assert _total("claude_tokens_entrada", "asistente") == 0 and _total("claude_tokens_salida", "asistente") == 0


def test_inv036_los_dos_llamadores_pasan_su_origen(client, monkeypatch):
    """`responder` del asistente y el de WhatsApp indican su origen al llamar a Claude."""
    origenes = []

    async def falsa(payload, origen="?"):
        origenes.append(origen)
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "hola"}], "usage": {}}

    monkeypatch.setattr(asistente, "llamar_claude", falsa)
    monkeypatch.setattr(wa, "llamar_claude", falsa)
    asyncio.run(asistente.responder("u1", "hola", []))
    asyncio.run(wa.responder("u1", "hola", "wamid.x"))
    assert origenes == ["asistente", "whatsapp"]


def test_inv036_fallo_al_contar_no_rompe_el_flujo(client, monkeypatch, capsys):
    """Si la tabla de contadores falla, el asistente responde normal y solo queda un aviso sin datos personales."""
    def falla(*a, **k):
        raise RuntimeError(f"falló la tabla de {CORREO} {TEL}")

    monkeypatch.setattr(contadores, "_incrementar_o_falla", falla)
    _claude_httpx(monkeypatch, {"stop_reason": "end_turn", "model": "m", "usage": {"input_tokens": 9, "output_tokens": 2},
                                "content": [{"type": "text", "text": "Respuesta normal"}]})
    r = client.post("/api/v1/asistente/chat", json={"pregunta": "hola"}, headers=auth_header("user-a"))
    assert r.status_code == 200 and r.json()["respuesta"] == "Respuesta normal"
    salida = capsys.readouterr().out
    assert "[contadores] Aviso" in salida and "RuntimeError" in salida
    assert CORREO not in salida and TEL not in salida and "falló la tabla" not in salida


def test_inv036_error_de_supabase_se_captura_y_no_filtra_el_mensaje(monkeypatch, capsys):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "clave-secreta-123")

    def cliente_roto():
        raise ConnectionError("clave-secreta-123 https://x.supabase.co caído")

    monkeypatch.setattr(contadores.SupabaseDB, "get_client", staticmethod(cliente_roto))
    assert contadores.incrementar("claude_llamadas", "asistente", 1) is False
    salida = capsys.readouterr().out
    assert "ConnectionError" in salida and "clave-secreta" not in salida and "supabase.co" not in salida


# ---------- Brevo ----------

class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code, self.text = status_code, text


@pytest.mark.parametrize("status,sumado", [(201, 1), (200, 1), (400, 0), (500, 0)])
def test_inv036_solo_cuentan_correos_exitosos(monkeypatch, status, sumado):
    monkeypatch.setattr(em.httpx, "post", lambda *a, **k: _Resp(status))
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setattr(settings, "FROM_EMAIL", "remitente@example.com")
    assert em.send_verification_email(CORREO, "123456") is (sumado == 1)
    assert _total("brevo_correos_enviados") == sumado


def test_inv036_correo_con_excepcion_de_red_no_cuenta(monkeypatch):
    def cae(*a, **k):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(em.httpx, "post", cae)
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setattr(settings, "FROM_EMAIL", "remitente@example.com")
    assert em.send_verification_email(CORREO, "123456") is False
    assert _total("brevo_correos_enviados") == 0


def test_inv036_fallo_al_contar_no_impide_el_correo(monkeypatch):
    monkeypatch.setattr(em.httpx, "post", lambda *a, **k: _Resp(201))
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setattr(settings, "FROM_EMAIL", "remitente@example.com")
    monkeypatch.setattr(contadores, "_incrementar_o_falla", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    assert em.send_verification_email(CORREO, "123456") is True


# ---------- WhatsApp: enviados ----------

def _meta_http(monkeypatch, status):
    monkeypatch.setattr(settings, "WHATSAPP_TOKEN", "token")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "123")
    real = _REAL_CLIENT
    monkeypatch.setattr(wa.httpx, "AsyncClient", lambda **kw: real(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, json={"error": {"code": 1, "message": "x"}})), **kw))


@pytest.mark.parametrize("status,sumado", [(200, 1), (400, 0), (500, 0)])
def test_inv036_whatsapp_enviados_solo_si_meta_acepta(monkeypatch, status, sumado):
    _meta_http(monkeypatch, status)
    assert asyncio.run(wa.enviar(TEL, "hola")) is (sumado == 1)
    assert _total("whatsapp_enviados") == sumado


def test_inv036_whatsapp_sin_conexion_no_cuenta(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_TOKEN", "token")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "123")

    def cae(request):
        raise httpx.ConnectError("sin red")

    real = _REAL_CLIENT
    monkeypatch.setattr(wa.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(cae), **kw))
    assert asyncio.run(wa.enviar(TEL, "hola")) is False
    assert _total("whatsapp_enviados") == 0


# ---------- WhatsApp: recibidos (webhook) ----------

@pytest.fixture
def webhook(client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_TOKEN", "token")
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", SECRETO)
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "palabra-secreta")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "clave")

    async def enviar(telefono, texto):
        return True

    monkeypatch.setattr(wa, "enviar", enviar)

    def enviar_mensaje(de, texto="ayuda", wamid="wamid.1", firma=True):
        cuerpo = json.dumps({"entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "123"},
            "messages": [{"id": wamid, "from": de, "type": "text", "text": {"body": texto}}]}}]}]}).encode()
        headers = {"Content-Type": "application/json"}
        if firma:
            headers["X-Hub-Signature-256"] = "sha256=" + hmac.new(SECRETO.encode(), cuerpo, hashlib.sha256).hexdigest()
        else:
            headers["X-Hub-Signature-256"] = "sha256=deadbeef"
        return client.post("/api/v1/whatsapp/webhook", content=cuerpo, headers=headers)

    return enviar_mensaje


def test_inv036_recibidos_solo_de_numeros_enlazados(webhook):
    whatsapp_db._Memoria.enlaces["usuario-1"] = TEL
    # número desconocido con firma válida: no cuenta
    assert webhook("573009998877", wamid="wamid.a").status_code == 200
    assert _total("whatsapp_recibidos") == 0
    # número enlazado con firma inválida: rechazado y no cuenta
    assert webhook(TEL, wamid="wamid.b", firma=False).status_code == 403
    assert _total("whatsapp_recibidos") == 0
    # número enlazado con firma válida: suma 1
    assert webhook(TEL, wamid="wamid.c").status_code == 200
    assert _total("whatsapp_recibidos") == 1


def test_inv036_recibidos_no_se_infla_con_reenvios_de_meta(webhook):
    whatsapp_db._Memoria.enlaces["usuario-1"] = TEL
    for _ in range(3):
        webhook(TEL, wamid="wamid.repetido")
    assert _total("whatsapp_recibidos") == 1


def test_inv036_un_numero_desconocido_con_codigo_invalido_tampoco_cuenta(webhook):
    webhook("573009998877", texto="FZ-000000", wamid="wamid.z")
    assert _total("whatsapp_recibidos") == 0


# ---------- Nada personal, lista fija, producción ----------

def test_inv036_nada_personal_se_guarda(webhook, monkeypatch):
    whatsapp_db._Memoria.enlaces["usuario-1"] = TEL
    webhook(TEL, texto="hola, soy " + CORREO, wamid="wamid.p")
    monkeypatch.setattr(em.httpx, "post", lambda *a, **k: _Resp(201))
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setattr(settings, "FROM_EMAIL", "remitente@example.com")
    em.send_verification_email(CORREO, "123456")
    contenido = repr(contadores._Memoria.filas) + repr(contadores.leer_ventana())
    assert contadores._Memoria.filas
    for secreto in (CORREO, TEL, "usuario-1", "hola", "persona"):
        assert secreto not in contenido
    for (fecha, metrica, origen), cantidad in contadores._Memoria.filas.items():
        assert metrica in contadores.METRICAS + (contadores.METRICA_PURGA,)
        assert origen in contadores.ORIGENES and type(cantidad) is int and cantidad >= 0


@pytest.mark.parametrize("metrica,origen,cantidad", [
    ("otra_metrica", "general", 1), ("claude_llamadas", "otro", 1), (CORREO, "general", 1),
    ("purga", "general", 1), ("claude_llamadas", "general", -1), ("claude_llamadas", "general", True),
    ("claude_llamadas", "general", 1.5), ("claude_llamadas", "general", 0),
])
def test_inv036_rechaza_metricas_origenes_y_cantidades_invalidas(metrica, origen, cantidad):
    assert contadores.incrementar(metrica, origen, cantidad) is False
    assert contadores._Memoria.filas == {}


def test_inv013_en_produccion_sin_supabase_no_se_guarda_en_memoria(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert contadores.incrementar("claude_llamadas", "asistente", 1) is False
    assert contadores._Memoria.filas == {}


# ---------- Purga y lectura ----------

def test_inv036_purga_a_90_dias_una_vez_al_dia():
    hoy = datetime.now(timezone.utc).date()
    F = contadores._Memoria.filas
    F[(hoy - timedelta(days=91), "claude_llamadas", "whatsapp")] = 5
    F[(hoy - timedelta(days=200), "purga", "general")] = 0
    F[(hoy - timedelta(days=90), "claude_llamadas", "whatsapp")] = 5
    F[(hoy - timedelta(days=1), "whatsapp_recibidos", "general")] = 3
    assert contadores.incrementar("whatsapp_enviados", "general", 1)
    assert set(F) == {(hoy - timedelta(days=90), "claude_llamadas", "whatsapp"),
                      (hoy - timedelta(days=1), "whatsapp_recibidos", "general"),
                      (hoy, "whatsapp_enviados", "general"), (hoy, "purga", "general")}
    # segunda escritura del mismo día: no vuelve a purgar
    F[(hoy - timedelta(days=120), "claude_llamadas", "whatsapp")] = 1
    contadores.incrementar("whatsapp_enviados", "general", 1)
    assert (hoy - timedelta(days=120), "claude_llamadas", "whatsapp") in F
    assert F[(hoy, "whatsapp_enviados", "general")] == 2


class _Rpc:
    def __init__(self, registro, nombre, args, falla):
        self.registro, self.nombre, self.args, self.falla = registro, nombre, args, falla

    def execute(self):
        self.registro.append((self.nombre, self.args))
        if self.falla == self.nombre:
            raise RuntimeError("falló")
        return type("R", (), {"data": None})()


class _Cliente:
    def __init__(self, falla=None):
        self.llamadas, self.falla = [], falla

    def rpc(self, nombre, args):
        return _Rpc(self.llamadas, nombre, args, self.falla)


def _con_supabase(monkeypatch, cliente):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "k")
    monkeypatch.setattr(contadores.SupabaseDB, "get_client", staticmethod(lambda: cliente))


def test_inv036_con_supabase_usa_rpc_atomico_y_purga_oportunista(monkeypatch):
    cliente = _Cliente()
    _con_supabase(monkeypatch, cliente)
    assert contadores.incrementar("claude_tokens_entrada", "whatsapp", 42) is True
    hoy = datetime.now(timezone.utc).date().isoformat()
    assert cliente.llamadas == [
        ("incrementar_contador", {"p_fecha": hoy, "p_metrica": "claude_tokens_entrada", "p_origen": "whatsapp", "p_cantidad": 42}),
        ("purgar_contadores", {"p_hoy": hoy}),
    ]


def test_inv036_fallo_de_la_purga_no_invalida_el_conteo(monkeypatch):
    _con_supabase(monkeypatch, _Cliente(falla="purgar_contadores"))
    assert contadores.incrementar("whatsapp_enviados", "general", 1) is True


def test_inv036_fallo_del_rpc_devuelve_false_sin_lanzar(monkeypatch):
    _con_supabase(monkeypatch, _Cliente(falla="incrementar_contador"))
    assert contadores.incrementar("whatsapp_enviados", "general", 1) is False


def test_leer_ventana_30_dias_sin_marca_de_purga():
    hoy = datetime.now(timezone.utc).date()
    F = contadores._Memoria.filas
    F[(hoy - timedelta(days=30), "whatsapp_enviados", "general")] = 9    # fuera de la ventana
    F[(hoy - timedelta(days=29), "whatsapp_enviados", "general")] = 2    # dentro (30 días incluido hoy)
    F[(hoy, "purga", "general")] = 0
    F[(hoy, "claude_llamadas", "asistente")] = 4
    assert contadores.leer_ventana() == [
        {"fecha": (hoy - timedelta(days=29)).isoformat(), "metrica": "whatsapp_enviados", "origen": "general", "cantidad": 2},
        {"fecha": hoy.isoformat(), "metrica": "claude_llamadas", "origen": "asistente", "cantidad": 4},
    ]
    assert contadores.fecha_mas_antigua() == (hoy - timedelta(days=30)).isoformat()   # no se limita a la ventana
    contadores._Memoria.limpiar()
    assert contadores.fecha_mas_antigua() is None and contadores.leer_ventana() == []
