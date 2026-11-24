"""
Pruebas del Monitor del Dueño (CHG-017, CT-010, INV-031 a INV-035, BDD-MONITOR).

Nunca se llama a APIs reales: `httpx.AsyncClient` se sustituye por un cliente con `MockTransport` que registra
todas las peticiones salientes. Las pruebas de INV-036 (contadores) están en `test_contadores.py`.
"""
import asyncio
import hmac
import threading
import time

import httpx
import pytest

from conftest import auth_header
from app.api import dueno as dueno_mod
from app.api.routes import monitor as monitor_routes
from app.api.routes import users as users_routes
from app.core.config import Settings, settings
from app.models import contadores
from app.models.user import UserDB
from app.utils import monitor_plataformas as mp

RUTA = "/api/v1/monitor/resumen"
DUENO = "dueno@ejemplo.com"
OTRO = "otra@ejemplo.com"
TOKENS = {
    "MONITOR_RAILWAY_TOKEN": "tok-railway-SECRETO-1",
    "MONITOR_ANTHROPIC_ADMIN_KEY": "sk-ant-admin-SECRETO-2",
    "MONITOR_META_TOKEN": "tok-meta-SECRETO-3",
    "MONITOR_SUPABASE_TOKEN": "tok-supabase-SECRETO-4",
    "MONITOR_VERCEL_TOKEN": "tok-vercel-SECRETO-5",
    "MONITOR_BREVO_KEY": "tok-brevo-SECRETO-6",
}
IDS = {
    "MONITOR_RAILWAY_PROJECT_ID": "proyecto-railway-123",
    "MONITOR_META_WABA_ID": "123456789012345",
    "MONITOR_VERCEL_TEAM_ID": "team_AbC123",
}
HOSTS_FIJOS = {"backboard.railway.com", "api.anthropic.com", "graph.facebook.com", "api.vercel.com", "api.brevo.com"}
_ClienteReal = httpx.AsyncClient


# ==================== ayudas ====================

@pytest.fixture(autouse=True)
def monitor_limpio():
    mp.limpiar_cache()
    monitor_routes._limite.reset()
    yield
    mp.limpiar_cache()
    monitor_routes._limite.reset()


def _alta(store: dict, correo: str, activo: bool = True) -> str:
    store[correo.lower()] = {
        "id": f"id-{correo.lower()}", "email": correo.lower(), "full_name": "Nombre",
        "hashed_password": "x", "is_active": activo, "currency": "COP", "session_version": 0,
    }
    return f"id-{correo.lower()}"


@pytest.fixture
def sesiones(users, monkeypatch):
    """OWNER_EMAIL con mayúsculas y espacios a propósito; dos usuarios con sesión válida."""
    monkeypatch.setattr(settings, "OWNER_EMAIL", "  DUENO@Ejemplo.com ")
    return {"dueno": auth_header(_alta(users, DUENO)), "otro": auth_header(_alta(users, OTRO)), "store": users}


def _respuesta_json(url: httpx.URL, request: httpx.Request):
    host, ruta = url.host, url.path
    if host == "backboard.railway.com":
        return {"data": {"estimatedUsage": [{"measurement": "CPU_USAGE", "estimatedValue": 120},
                                            {"measurement": "MEMORY_USAGE_GB", "estimatedValue": 600}]}}
    if host == "api.anthropic.com" and ruta.endswith("usage_report/messages"):
        return {"data": [{"results": [{"uncached_input_tokens": 100, "cache_read_input_tokens": 10,
                                       "cache_creation": {"ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": 5},
                                       "output_tokens": 50}]}]}
    if host == "api.anthropic.com" and ruta.endswith("cost_report"):
        return {"data": [{"results": [{"amount": "250.5", "currency": "USD"}]}]}
    if host == "graph.facebook.com":
        return {"pricing_analytics": {"data": [{"data_points": [{"volume": 7, "cost": 1.5}, {"volume": 3}]}]}}
    if host == "api.vercel.com":
        return {"billing": {"plan": "hobby"}}
    if host == "api.brevo.com" and ruta.endswith("/account"):
        return {"plan": [{"type": "free", "creditsType": "sendLimit", "credits": 280}]}
    if host == "api.brevo.com" and ruta.endswith("aggregatedReport"):
        return {"requests": 20}
    return None


class Salientes:
    """Peticiones salientes registradas; `respuestas` permite sustituir la respuesta de un host."""

    def __init__(self):
        self.peticiones: list[httpx.Request] = []
        self.por_host: dict[str, object] = {}   # host -> función(request) -> Response | corrutina

    def hosts(self) -> list[str]:
        return [r.url.host for r in self.peticiones]

    def a(self, host: str) -> list[httpx.Request]:
        return [r for r in self.peticiones if r.url.host == host]


@pytest.fixture
def externas(monkeypatch):
    """Configura los tokens/ids y simula las plataformas con httpx (MockTransport)."""
    for clave, valor in {**TOKENS, **IDS}.items():
        monkeypatch.setattr(settings, clave, valor)
    registro = Salientes()

    async def manejador(request: httpx.Request):
        registro.peticiones.append(request)
        propio = registro.por_host.get(request.url.host)
        if propio is not None:
            resultado = propio(request)
            return await resultado if asyncio.iscoroutine(resultado) else resultado
        cuerpo = _respuesta_json(request.url, request)
        return httpx.Response(200, json=cuerpo) if cuerpo is not None else httpx.Response(404)

    class ClienteSimulado(_ClienteReal):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(manejador)   # el resto (follow_redirects...) es el del código
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", ClienteSimulado)
    return registro


def _sin_date(resp) -> tuple:
    cabeceras = sorted((k.lower(), v) for k, v in resp.headers.items() if k.lower() != "date")
    return resp.status_code, resp.content, cabeceras


def _datos(resp, plataforma: str):
    return resp.json()["plataformas"][plataforma]


# ==================== INV-031 ====================

def test_inv031_correo_con_mayusculas_y_espacios(client, sesiones, externas):
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert set(cuerpo) == {"generado_en", "contadores", "plataformas"}
    assert set(cuerpo["plataformas"]) == {"railway", "anthropic", "meta", "supabase", "vercel", "brevo"}
    assert cuerpo["generado_en"].endswith("Z")
    assert cuerpo["contadores"] == {"desde": None, "dias": []}
    assert _datos(r, "railway")["estado"] == "ok"
    assert _datos(r, "brevo")["datos"] == {"creditos_restantes": 280, "enviados_hoy": 20}
    assert _datos(r, "anthropic")["datos"] == {
        "tokens_entrada_mes": 115, "tokens_salida_mes": 50, "costo_mes": 2.505, "moneda": "USD"}
    assert _datos(r, "meta")["datos"]["conversaciones_periodo"] == 10
    assert _datos(r, "vercel")["datos"] == {"plan": "gratuito"}
    assert _datos(r, "railway")["datos"]["uso_cpu_vcpu_horas"] == 2.0
    assert _datos(r, "railway")["datos"]["uso_memoria_gb_horas"] == 10.0
    for p in cuerpo["plataformas"].values():
        assert set(p) == {"estado", "datos", "actualizado_en"}


def test_inv031_no_dueno_recibe_404_identico_a_ruta_inexistente(client, sesiones, externas):
    r = client.get(RUTA, headers=sesiones["otro"])
    inexistente = client.get("/api/v1/no-existe", headers=sesiones["otro"])
    sin_monitor = client.get("/api/v1/monitor/no-existe", headers=sesiones["otro"])
    assert r.status_code == 404
    assert _sin_date(r) == _sin_date(inexistente) == _sin_date(sin_monitor)
    for resp in (r, inexistente, sin_monitor):
        assert "cache-control" not in resp.headers
    assert r.json() == {"detail": "Not Found"}
    minusculas = r.text.lower()
    assert "monitor" not in minusculas and DUENO not in minusculas and "dueño" not in minusculas
    assert externas.peticiones == []   # no se consulta nada a nadie que no sea el Dueño


def test_inv031_sin_sesion_recibe_404(client, sesiones, externas):
    r = client.get(RUTA)
    assert r.status_code == 404
    assert _sin_date(r) == _sin_date(client.get("/api/v1/no-existe"))
    # también con un token basura o con un esquema distinto
    for cabecera in ({"Authorization": "Bearer basura"}, {"Authorization": "Basic abc"}, {"Authorization": ""}):
        assert _sin_date(client.get(RUTA, headers=cabecera)) == _sin_date(r)
    assert externas.peticiones == []


@pytest.mark.parametrize("valor", ["", "   "])
def test_inv031_sin_owner_email_responde_404(client, sesiones, externas, monkeypatch, valor):
    monkeypatch.setattr(settings, "OWNER_EMAIL", valor)
    r = client.get(RUTA, headers=sesiones["dueno"])   # ni siquiera el Dueño habitual
    assert r.status_code == 404
    assert _sin_date(r) == _sin_date(client.get("/api/v1/no-existe"))
    assert externas.peticiones == []


def test_inv031_owner_email_ausente_en_el_entorno(monkeypatch):
    monkeypatch.delenv("OWNER_EMAIL", raising=False)
    assert Settings(_env_file=None).OWNER_EMAIL == ""   # sin autocorrección: vacío = nadie es Dueño
    monkeypatch.setenv("OWNER_EMAIL", "  MAYUS@Ejemplo.COM ")
    config = Settings(_env_file=None)
    assert config.OWNER_EMAIL == "mayus@ejemplo.com"
    assert "mayus@ejemplo.com" not in repr(config) and "mayus@ejemplo.com" not in str(config)


def test_inv031_sin_owner_email_ni_se_mira_la_sesion(client, sesiones, externas, monkeypatch):
    vistos = []

    async def espia(user_id):
        vistos.append(user_id)
        return {"email": DUENO}

    monkeypatch.setattr(settings, "OWNER_EMAIL", "")
    monkeypatch.setattr(UserDB, "get_by_id", staticmethod(espia))
    assert client.get(RUTA, headers=sesiones["dueno"]).status_code == 404
    assert vistos == []


def test_inv031_bd_caida_al_autorizar_responde_404(client, sesiones, externas, monkeypatch):
    async def falla(_user_id):
        raise RuntimeError("Supabase caído")
    monkeypatch.setattr(UserDB, "get_session_version", staticmethod(falla))
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert r.status_code == 404   # no 503
    assert _sin_date(r) == _sin_date(client.get("/api/v1/no-existe"))
    assert "cache-control" not in r.headers
    assert externas.peticiones == []


def test_inv031_bd_caida_al_leer_el_usuario_responde_404(client, sesiones, externas, monkeypatch):
    async def falla(_user_id):
        raise RuntimeError("Supabase caído")
    monkeypatch.setattr(UserDB, "get_by_id", staticmethod(falla))
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert r.status_code == 404
    assert _sin_date(r) == _sin_date(client.get("/api/v1/no-existe"))


def test_inv031_cuenta_inactiva_o_sesion_vieja_recibe_404(client, sesiones, externas):
    sesiones["store"][DUENO]["is_active"] = False   # INV-017
    assert client.get(RUTA, headers=sesiones["dueno"]).status_code == 404
    sesiones["store"][DUENO]["is_active"] = True
    sesiones["store"][DUENO]["session_version"] = 1   # INV-016: el token trae versión 0
    assert client.get(RUTA, headers=sesiones["dueno"]).status_code == 404


def test_inv031_bd_caida_al_leer_contadores_responde_503_solo_al_dueno(client, sesiones, externas, monkeypatch):
    def falla():
        raise RuntimeError("tabla contadores caída")
    monkeypatch.setattr(contadores, "leer_ventana", falla)
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert r.status_code == 503
    assert r.headers["cache-control"] == "no-store"
    assert "caída" not in r.text and "tabla" not in r.text and "RuntimeError" not in r.text   # sin el motivo
    o = client.get(RUTA, headers=sesiones["otro"])   # misma situación, no es el Dueño
    assert o.status_code == 404
    assert _sin_date(o) == _sin_date(client.get("/api/v1/no-existe"))
    assert "cache-control" not in o.headers


def test_inv031_usa_compare_digest(client, sesiones, externas, monkeypatch):
    """Se inyecta un `hmac` PROPIO solo en `app.api.dueno` (el módulo global `hmac` no se toca: PyJWT lo usa)."""
    llamadas = []

    class HmacEspia:
        @staticmethod
        def compare_digest(a, b):
            llamadas.append((a, b))
            return hmac.compare_digest(a, b)

    monkeypatch.setattr(dueno_mod, "hmac", HmacEspia)
    assert client.get(RUTA, headers=sesiones["dueno"]).status_code == 200
    assert llamadas == [(b"dueno@ejemplo.com", b"dueno@ejemplo.com")]
    llamadas.clear()
    assert client.get(RUTA, headers=sesiones["otro"]).status_code == 404
    assert llamadas == [(b"otra@ejemplo.com", b"dueno@ejemplo.com")]


def test_inv031_users_me_es_dueno_solo_informa_sobre_si_mismo(client, sesiones, monkeypatch):
    r = client.get("/api/v1/users/me", headers=sesiones["dueno"])
    assert r.status_code == 200 and r.json()["es_dueno"] is True
    o = client.get("/api/v1/users/me", headers=sesiones["otro"])
    assert o.status_code == 200 and o.json()["es_dueno"] is False
    assert DUENO not in o.text.lower()   # nunca el correo del dueño a otro usuario
    # los PUT devuelven lo mismo que GET /users/me (CT-002)
    p = client.put("/api/v1/users/me", headers=sesiones["dueno"], json={"full_name": "Nombre Nuevo"})
    assert p.status_code == 200 and p.json()["es_dueno"] is True
    # sin OWNER_EMAIL: false y sigue respondiendo 200
    monkeypatch.setattr(settings, "OWNER_EMAIL", "")
    v = client.get("/api/v1/users/me", headers=sesiones["dueno"])
    assert v.status_code == 200 and v.json()["es_dueno"] is False
    # si la comprobación falla: false y 200
    monkeypatch.setattr(settings, "OWNER_EMAIL", DUENO)

    def rota(_correo):
        raise RuntimeError("fallo")
    monkeypatch.setattr(users_routes, "es_correo_dueno", rota)
    f = client.get("/api/v1/users/me", headers=sesiones["dueno"])
    assert f.status_code == 200 and f.json()["es_dueno"] is False


def test_es_dueno_no_puede_venir_de_la_bd(client, sesiones):
    sesiones["store"][OTRO]["es_dueno"] = True   # aunque la «fila» lo traiga, se recalcula en el servidor
    assert client.get("/api/v1/users/me", headers=sesiones["otro"]).json()["es_dueno"] is False


# ==================== INV-033 ====================

@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE", "HEAD"])
def test_inv033_dueno_con_metodo_no_get_recibe_405(client, sesiones, externas, metodo):
    r = client.request(metodo, RUTA, headers=sesiones["dueno"])
    assert r.status_code == 405
    assert r.headers["cache-control"] == "no-store"
    assert externas.peticiones == []   # no se ejecutó nada


@pytest.mark.parametrize("metodo", ["POST", "HEAD"])
def test_inv033_no_dueno_con_post_recibe_404_identico(client, sesiones, externas, metodo):
    r = client.request(metodo, RUTA, headers=sesiones["otro"])
    esperado = client.request(metodo, "/api/v1/no-existe", headers=sesiones["otro"])
    assert r.status_code == 404 and r.status_code != 405
    assert _sin_date(r) == _sin_date(esperado)
    assert "cache-control" not in r.headers
    for m in ("PUT", "PATCH", "DELETE", "GET"):   # cualquier método
        assert client.request(m, RUTA, headers=sesiones["otro"]).status_code == 404
    assert client.request("POST", RUTA).status_code == 404   # y sin sesión


def test_inv033_no_se_escribe_en_plataformas(client, sesiones, externas):
    antes = dict(contadores._Memoria.filas)
    assert client.get(RUTA, headers=sesiones["dueno"]).status_code == 200
    for metodo in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(metodo, RUTA, headers=sesiones["dueno"]).status_code == 405
    assert externas.peticiones, "debería haberse consultado alguna plataforma"
    for p in externas.peticiones:
        if p.method == "POST":   # única excepción: GraphQL de Railway, solo con una consulta de lectura
            assert p.url.host == "backboard.railway.com"
            cuerpo = p.content.decode()
            assert cuerpo.startswith('{"query":"query(') and "mutation" not in cuerpo.lower()
        else:
            assert p.method == "GET"
    assert contadores._Memoria.filas == antes   # nada se escribe en la tabla de contadores desde /monitor/*


@pytest.mark.parametrize("metodo", ["GET", "POST", "DELETE"])
def test_inv033_subruta_inexistente_responde_404_normal(client, sesiones, externas, metodo):
    esperado_sin_sesion = client.get("/api/v1/no-existe")
    for cabeceras in ({}, sesiones["otro"], sesiones["dueno"]):   # el Dueño también recibe el 404 normal
        r = client.request(metodo, "/api/v1/monitor/no-existe", headers=cabeceras)
        assert r.status_code == 404
        assert "cache-control" not in r.headers
        if metodo == "GET":
            assert _sin_date(r) == _sin_date(esperado_sin_sesion)
    # ni 405 ni 429 aunque el Dueño ya haya gastado su cupo
    for _ in range(25):
        client.get(RUTA, headers=sesiones["dueno"])
    assert client.request(metodo, "/api/v1/monitor/no-existe", headers=sesiones["dueno"]).status_code == 404


def test_inv033_options_responde_igual_en_cualquier_ruta(client, sesiones):
    cabeceras = {"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET",
                 "Access-Control-Request-Headers": "Authorization"}
    a = client.options(RUTA, headers=cabeceras)
    b = client.options("/api/v1/no-existe", headers=cabeceras)
    assert a.status_code == b.status_code == 200
    assert _sin_date(a) == _sin_date(b)
    assert "monitor" not in a.text.lower()


@pytest.mark.parametrize("metodo", ["TRACE", "FOO", "PROPFIND", "OPTIONS", "CONNECT"])
def test_inv033_metodos_raros_no_dueno_recibe_404_identico_byte_a_byte(client, sesiones, externas, metodo):
    """Sin Origin ni cabeceras de preflight, OPTIONS no lo atiende el middleware CORS: llega a la ruta."""
    for cabeceras in ({}, sesiones["otro"]):
        r = client.request(metodo, RUTA, headers=cabeceras)
        esperado = client.request(metodo, "/api/v1/no-existe", headers=cabeceras)
        assert r.status_code == 404
        assert r.content == esperado.content and _sin_date(r) == _sin_date(esperado)
        assert "cache-control" not in r.headers and "allow" not in r.headers
    assert externas.peticiones == []


@pytest.mark.parametrize("metodo", ["TRACE", "FOO", "PROPFIND", "OPTIONS"])
def test_inv033_metodos_raros_dueno_recibe_405_con_no_store(client, sesiones, externas, metodo):
    r = client.request(metodo, RUTA, headers=sesiones["dueno"])
    assert r.status_code == 405
    assert r.headers["cache-control"] == "no-store" and r.headers["allow"] == "GET"
    assert externas.peticiones == []


def test_inv031_barra_final_es_404_como_cualquier_ruta_inexistente(client, sesiones, externas):
    for cabeceras in ({}, sesiones["otro"], sesiones["dueno"]):
        r = client.get(RUTA + "/", headers=cabeceras, follow_redirects=False)
        esperado = client.get("/api/v1/no-existe/", headers=cabeceras, follow_redirects=False)
        assert r.status_code == 404 and "location" not in r.headers   # ni 307 ni redirección alguna
        assert r.content == esperado.content and _sin_date(r) == _sin_date(esperado)
    assert externas.peticiones == []


# ==================== plataformas ====================

def test_plataforma_caida_no_rompe_las_demas(client, sesiones, externas, monkeypatch):
    monkeypatch.setattr(settings, "MONITOR_ANTHROPIC_ADMIN_KEY", "")   # falta el token
    externas.por_host["backboard.railway.com"] = lambda r: httpx.Response(500, text="boom TOKEN-INTERNO")
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert r.status_code == 200
    for caida in ("railway", "anthropic"):
        assert _datos(r, caida) == {"estado": "no_disponible", "datos": None, "actualizado_en": None}
    for viva in ("meta", "vercel", "brevo"):
        assert _datos(r, viva)["estado"] == "ok" and _datos(r, viva)["datos"]
    assert "boom" not in r.text and "TOKEN-INTERNO" not in r.text and "500" not in r.text


def test_anthropic_sin_filas_omite_los_tokens_en_vez_de_devolver_cero(client, sesiones, externas):
    externas.por_host["api.anthropic.com"] = lambda r: httpx.Response(
        200, json={"data": [{"results": [{"amount": "100", "currency": "USD"}]}]} if r.url.path.endswith("cost_report")
        else {"data": []})
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, "anthropic")["datos"] == {"costo_mes": 1.0, "moneda": "USD"}   # sin tokens_*_mes


def test_anthropic_cada_informe_se_envuelve_por_separado(client, sesiones, externas):
    # el informe de uso viene con forma rara (lanza al aplanarlo): el de costo debe sobrevivir, y al revés
    def respuesta(r):
        if r.url.path.endswith("usage_report/messages"):
            return httpx.Response(200, json={"forma": "rara"})
        return httpx.Response(200, json={"data": [{"results": [{"amount": "250", "currency": "USD"}]}]})

    externas.por_host["api.anthropic.com"] = respuesta
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, "anthropic")["datos"] == {"costo_mes": 2.5, "moneda": "USD"}
    mp.limpiar_cache()
    externas.por_host["api.anthropic.com"] = lambda r: (
        httpx.Response(200, json={"data": [{"results": [{"output_tokens": 7}]}]})
        if r.url.path.endswith("usage_report/messages") else httpx.Response(200, json=[1, 2]))
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, "anthropic")["datos"] == {"tokens_salida_mes": 7}


def test_inv034_cuerpo_de_plataforma_mayor_de_1mb_es_no_disponible(client, sesiones, externas):
    assert mp.MAX_CUERPO == 1_000_000
    relleno = "x" * (mp.MAX_CUERPO + 10)
    # sin Content-Length fiable (el cuerpo se corta al leerlo) y con él
    externas.por_host["api.vercel.com"] = lambda r: httpx.Response(200, json={"billing": {"plan": "pro"}, "r": relleno})
    externas.por_host["api.brevo.com"] = lambda r: httpx.Response(
        200, content=b'{"requests": 1}', headers={"Content-Length": str(mp.MAX_CUERPO + 1)})
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, "vercel")["estado"] == "no_disponible"
    assert _datos(r, "brevo")["estado"] == "no_disponible"
    assert _datos(r, "meta")["estado"] == "ok"
    # justo en el límite sí vale
    mp.limpiar_cache()
    ajustado = '{"billing": {"plan": "pro"}, "r": "' + "x" * (mp.MAX_CUERPO - 40) + '"}'
    assert len(ajustado) <= mp.MAX_CUERPO
    externas.por_host["api.vercel.com"] = lambda r: httpx.Response(200, content=ajustado.encode())
    assert _datos(client.get(RUTA, headers=sesiones["dueno"]), "vercel")["datos"] == {"plan": "pro"}


def test_supabase_queda_no_disponible_sin_consultar(client, sesiones, externas):
    # Pendiente documentado (ADR-008): no hay GET de solo lectura con el tamaño de la BD
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, "supabase")["estado"] == "no_disponible"
    assert "api.supabase.com" not in externas.hosts()


def test_anthropic_exige_clave_de_administracion(client, sesiones, externas, monkeypatch):
    monkeypatch.setattr(settings, "MONITOR_ANTHROPIC_ADMIN_KEY", "sk-ant-api03-no-es-de-admin")
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, "anthropic")["estado"] == "no_disponible"
    assert "api.anthropic.com" not in externas.hosts()   # ni se envía la clave equivocada


def test_inv032_no_se_filtran_tokens_en_respuesta_ni_logs(client, sesiones, externas, capsys, caplog):
    secretos = [*TOKENS.values(), DUENO, "+573001112233", "texto-libre-privado"]

    def error_con_token(req):
        raise httpx.ConnectError(f"fallo al conectar con {req.url} con {req.headers}")

    externas.por_host["backboard.railway.com"] = error_con_token
    externas.por_host["api.anthropic.com"] = lambda r: httpx.Response(
        401, json={"error": {"message": f"clave {TOKENS['MONITOR_ANTHROPIC_ADMIN_KEY']} inválida"}})
    externas.por_host["graph.facebook.com"] = lambda r: httpx.Response(400, text=TOKENS["MONITOR_META_TOKEN"])
    externas.por_host["api.vercel.com"] = lambda r: httpx.Response(
        200, text="no es json " + TOKENS["MONITOR_VERCEL_TOKEN"])
    externas.por_host["api.brevo.com"] = lambda r: httpx.Response(
        200, json={"email": DUENO, "phone": "+573001112233", "texto": "texto-libre-privado"})
    with caplog.at_level("DEBUG"):
        r = client.get(RUTA, headers=sesiones["dueno"])
    salida = capsys.readouterr()
    todo = r.text + salida.out + salida.err + caplog.text
    for secreto in secretos:
        assert secreto not in todo, secreto
    assert r.status_code == 200
    for nombre in ("railway", "anthropic", "meta", "vercel", "brevo", "supabase"):
        assert _datos(r, nombre)["estado"] == "no_disponible"
    assert "backboard.railway.com" not in todo and "Authorization" not in todo   # sin URL ni cabeceras en logs


def test_inv032_log_lleva_motivo_http_401_sin_token_ni_cuerpo(client, sesiones, externas, capsys, caplog):
    cuerpo_error = "CUERPO-DE-ERROR-PRIVADO"
    externas.por_host["backboard.railway.com"] = lambda r: httpx.Response(
        401, json={"error": f"{cuerpo_error} {TOKENS['MONITOR_RAILWAY_TOKEN']}"})
    with caplog.at_level("DEBUG"):
        r = client.get(RUTA, headers=sesiones["dueno"])
    salida = capsys.readouterr()
    todo = r.text + salida.out + salida.err + caplog.text
    assert "[monitor] railway: no disponible (_NoDisponible: http_401)" in salida.out
    assert _datos(r, "railway") == {"estado": "no_disponible", "datos": None, "actualizado_en": None}
    assert "http_401" not in r.text   # INV-032: el motivo no sale al cliente
    assert cuerpo_error not in todo and TOKENS["MONITOR_RAILWAY_TOKEN"] not in todo


def test_inv032_log_lleva_motivo_graphql_errors_sin_cuerpo(client, sesiones, externas, capsys, caplog):
    mensaje = "MENSAJE-GRAPHQL-PRIVADO"
    externas.por_host["backboard.railway.com"] = lambda r: httpx.Response(
        200, json={"errors": [{"message": f"{mensaje} {TOKENS['MONITOR_RAILWAY_TOKEN']}"}]})
    with caplog.at_level("DEBUG"):
        r = client.get(RUTA, headers=sesiones["dueno"])
    salida = capsys.readouterr()
    todo = r.text + salida.out + salida.err + caplog.text
    assert "[monitor] railway: no disponible (_NoDisponible: graphql_errors)" in salida.out
    assert _datos(r, "railway")["estado"] == "no_disponible"
    assert mensaje not in todo and TOKENS["MONITOR_RAILWAY_TOKEN"] not in todo


@pytest.mark.parametrize("respuesta,motivo", [
    (lambda r: httpx.Response(403), "http_403"),
    (lambda r: httpx.Response(404), "http_404"),
    (lambda r: httpx.Response(429), "http_429"),
    (lambda r: httpx.Response(503), "http_5xx"),
    (lambda r: httpx.Response(302, headers={"location": "https://otro.example/x"}), "redireccion"),
    (lambda r: httpx.Response(200, text="no es json"), "json_invalido"),
    (lambda r: httpx.Response(200, json=[1, 2]), "forma_inesperada"),
    (lambda r: httpx.Response(200, json={"data": {"estimatedUsage": []}}), "sin_campos"),
])
def test_inv032_motivos_de_lista_cerrada_en_el_log(client, sesiones, externas, capsys, respuesta, motivo):
    externas.por_host["backboard.railway.com"] = respuesta
    client.get(RUTA, headers=sesiones["dueno"])
    assert f"[monitor] railway: no disponible (_NoDisponible: {motivo})" in capsys.readouterr().out
    assert motivo in mp.MOTIVOS


def test_inv032_motivo_token_vacio_en_el_log(client, sesiones, externas, capsys, monkeypatch):
    monkeypatch.setattr(settings, "MONITOR_RAILWAY_TOKEN", "")
    client.get(RUTA, headers=sesiones["dueno"])
    assert "[monitor] railway: no disponible (_NoDisponible: token_vacio)" in capsys.readouterr().out


def test_nodisponible_ignora_motivos_fuera_de_la_lista():
    assert mp._NoDisponible("texto libre con secreto").motivo is None
    assert mp._NoDisponible().motivo is None


def test_inv032_settings_no_expone_tokens_en_repr():
    texto = repr(settings) + str(settings)
    for nombre in (*TOKENS, *IDS, "OWNER_EMAIL"):
        assert nombre not in texto


def test_inv032_datos_solo_lista_blanca(client, sesiones, externas, monkeypatch):
    hostil_brevo = {"creditos_restantes": True, "enviados_hoy": -5, "email": DUENO,
                    "telefono": "+573001112233", "texto": "hola", "token": TOKENS["MONITOR_BREVO_KEY"],
                    "plan": {"anidado": 1}}
    hostil_vercel = {"plan": "enterprise-hack", "ancho_banda_bytes": float("nan"),
                     "limite_ancho_banda_bytes": 100, "otro": [1, 2], "correo": DUENO}
    hostil_railway = {"costo_estimado_mes": float("inf"), "moneda": "EUR", "uso_cpu_vcpu_horas": 3,
                      "periodo_hasta": "2026-11-30T00:00:00+00:00", "uso_memoria_gb_horas": "12",
                      "secreto": "x"}
    hostil_meta = {"conversaciones_periodo": 4.5, "periodo_desde": "2026-11-01T10:00:00Z",
                   "periodo_hasta": "ayer", "extra": {"a": 1}}

    async def fabrica(valor):
        return valor

    for nombre, valor in (("brevo", hostil_brevo), ("vercel", hostil_vercel),
                          ("railway", hostil_railway), ("meta", hostil_meta)):
        monkeypatch.setitem(mp._CLIENTES, nombre, lambda _c, v=valor: fabrica(v))
    monkeypatch.setitem(mp._CLIENTES, "anthropic", lambda _c: fabrica(
        {"costo_mes": 1.5, "moneda": "USD", "tokens_entrada_mes": 10, "tokens_salida_mes": False,
         "cuenta": DUENO, "organizacion": "x"}))
    monkeypatch.setitem(mp._CLIENTES, "supabase", lambda _c: fabrica({"tamano_bd_bytes": 1, "texto": "x"}))
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert r.status_code == 200
    assert _datos(r, "brevo") == {"estado": "no_disponible", "datos": None, "actualizado_en": None}   # nada válido
    assert _datos(r, "vercel")["datos"] == {"limite_ancho_banda_bytes": 100}
    assert _datos(r, "railway")["datos"] == {"uso_cpu_vcpu_horas": 3}
    assert _datos(r, "meta")["datos"] == {"conversaciones_periodo": 4.5, "periodo_desde": "2026-11-01T10:00:00Z"}
    assert _datos(r, "anthropic")["datos"] == {"costo_mes": 1.5, "moneda": "USD", "tokens_entrada_mes": 10}
    assert _datos(r, "supabase")["datos"] == {"tamano_bd_bytes": 1}
    for nombre, p in r.json()["plataformas"].items():
        if p["datos"] is None:
            continue
        assert set(p["datos"]) <= set(mp.ESQUEMA[nombre])
        for v in p["datos"].values():
            assert type(v) in (int, float, str) and type(v) is not bool
    assert DUENO not in r.text and "+57" not in r.text


def test_inv032_respuesta_real_hostil_de_brevo_solo_deja_lo_valido(client, sesiones, externas):
    externas.por_host["api.brevo.com"] = lambda r: httpx.Response(200, json={
        "email": DUENO, "phone": "+573001112233",
        "plan": [{"creditsType": "sendLimit", "credits": True}, {"creditsType": "sendLimit", "credits": -3},
                 {"creditsType": "otro", "credits": 99}, {"creditsType": "sendLimit", "credits": 300}],
        "requests": "muchos"})
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, "brevo")["datos"] == {"creditos_restantes": 300}
    assert DUENO not in r.text and "+573" not in r.text


def test_filtrar_unidad():
    assert mp.filtrar("brevo", {"creditos_restantes": 5, "x": 1}) == {"creditos_restantes": 5}
    assert mp.filtrar("brevo", {"creditos_restantes": True}) is None
    assert mp.filtrar("brevo", "texto") is None
    assert mp.filtrar("inexistente", {"a": 1}) is None
    assert mp.filtrar("vercel", {"plan": "pro"}) == {"plan": "pro"}
    assert mp.filtrar("meta", {"periodo_desde": "2026-13-45"}) is None   # fecha imposible


def test_inv034_no_sigue_redirecciones(client, sesiones, externas):
    externas.por_host["api.brevo.com"] = lambda r: httpx.Response(
        302, headers={"Location": "https://evil.example/robar"})
    externas.por_host["evil.example"] = lambda r: httpx.Response(200, json={"requests": 1})
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, "brevo")["estado"] == "no_disponible"
    assert "evil.example" not in externas.hosts()
    assert _datos(r, "meta")["estado"] == "ok"


@pytest.mark.parametrize("malo", ["../x", "a?b=1", "a/b", "a b", "a#b", "x" * 65, "a\nb", "%2e%2e"])
@pytest.mark.parametrize("variable,host,plataforma", [
    ("MONITOR_RAILWAY_PROJECT_ID", "backboard.railway.com", "railway"),
    ("MONITOR_META_WABA_ID", "graph.facebook.com", "meta"),
    ("MONITOR_VERCEL_TEAM_ID", "api.vercel.com", "vercel"),
])
def test_inv034_id_invalido_deja_la_plataforma_no_disponible_sin_consultar(
        client, sesiones, externas, monkeypatch, variable, host, plataforma, malo):
    monkeypatch.setattr(settings, variable, malo)
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, plataforma)["estado"] == "no_disponible"
    assert host not in externas.hosts()
    assert _datos(r, "brevo")["estado"] == "ok"   # las demás con normalidad


def test_meta_usa_pricing_analytics_diario_sin_dimensions(client, sesiones, externas):
    client.get(RUTA, headers=sesiones["dueno"])
    campos = externas.a("graph.facebook.com")[0].url.params["fields"]
    assert campos.startswith("pricing_analytics.start(") and ".granularity(DAILY)" in campos
    assert "conversation_analytics" not in campos and "dimensions" not in campos


def test_meta_200_sin_pricing_analytics_es_cero_facturables(client, sesiones, externas):
    externas.por_host["graph.facebook.com"] = lambda r: httpx.Response(200, json={"id": "123"})
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, "meta")["estado"] == "ok"
    assert _datos(r, "meta")["datos"]["conversaciones_periodo"] == 0


def test_meta_suma_volume_ignorando_valores_invalidos(client, sesiones, externas):
    cuerpo = {"pricing_analytics": {"data": [{"data_points": [
        {"volume": 4}, {"volume": -2}, {"volume": True}, {"volume": "9"}, {"cost": 3}]},
        {"data_points": [{"volume": 6}]}]}}
    externas.por_host["graph.facebook.com"] = lambda r: httpx.Response(200, json=cuerpo)
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, "meta")["datos"]["conversaciones_periodo"] == 10


def test_meta_400_es_no_disponible(client, sesiones, externas):
    externas.por_host["graph.facebook.com"] = lambda r: httpx.Response(400, json={"error": {"message": "x"}})
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, "meta")["estado"] == "no_disponible"
    assert _datos(r, "brevo")["estado"] == "ok"


def test_inv034_version_de_graph_invalida_no_llega_a_la_url(client, sesiones, externas, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_GRAPH_VERSION", "v1/../../x")
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert _datos(r, "meta")["estado"] == "no_disponible"
    assert "graph.facebook.com" not in externas.hosts()


def test_inv034_nada_del_cliente_llega_a_la_url(client, sesiones, externas):
    cabeceras = {**sesiones["dueno"], "X-Forwarded-Host": "evil.example", "Origin": "https://evil.example",
                 "Referer": "https://evil.example/../x", "X-Url": "https://evil.example", "X-Id": "../../etc"}
    r = client.get(RUTA + "?url=https://evil.example&host=evil.example&id=../../etc&fields=evil&team=evil",
                   headers=cabeceras)
    assert r.status_code == 200
    assert externas.peticiones
    for p in externas.peticiones:
        assert p.url.host in HOSTS_FIJOS and p.url.scheme == "https"
        visto = f"{p.url} {dict(p.headers)} {p.content.decode()}"
        assert "evil" not in visto and "etc" not in visto.replace("estimatedUsage", "")


def test_inv034_timeout_de_5s_marca_no_disponible(client, sesiones, externas, monkeypatch):
    assert mp.TIMEOUT_TOTAL == 5.0   # el valor real; abajo se acorta solo para no esperar 5 s
    monkeypatch.setattr(mp, "TIMEOUT_TOTAL", 0.3)

    async def lenta(_r):
        await asyncio.sleep(30)   # cada fase de la conexión sería «rápida»: solo el plazo total la corta
        return httpx.Response(200, json={"requests": 1})

    externas.por_host["api.brevo.com"] = lenta
    t0 = time.monotonic()
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert time.monotonic() - t0 < 2
    assert _datos(r, "brevo") == {"estado": "no_disponible", "datos": None, "actualizado_en": None}
    assert _datos(r, "railway")["estado"] == "ok"


def test_inv034_resumen_responde_en_menos_de_6s_en_el_peor_caso(client, sesiones, externas, monkeypatch):
    async def lenta(_r):
        await asyncio.sleep(60)
        return httpx.Response(200, json={})

    for host in HOSTS_FIJOS:
        externas.por_host[host] = lenta

    async def supabase_lenta(_c):
        await asyncio.sleep(60)
        return {"tamano_bd_bytes": 1}

    monkeypatch.setitem(mp._CLIENTES, "supabase", supabase_lenta)
    inicio_lectura = []

    def lectura_normal():
        inicio_lectura.append(time.monotonic())
        return [], None

    monkeypatch.setattr(contadores, "leer_ventana", lectura_normal)
    t0 = time.monotonic()
    r = client.get(RUTA, headers=sesiones["dueno"])
    total = time.monotonic() - t0
    assert r.status_code == 200
    assert total < 6, total
    assert all(p["estado"] == "no_disponible" for p in r.json()["plataformas"].values())
    assert inicio_lectura and inicio_lectura[0] - t0 < 1   # los contadores no esperaron a las plataformas


def test_inv034_lectura_de_contadores_con_plazo_total_503_solo_al_dueno(client, sesiones, externas, monkeypatch):
    assert monitor_routes.PLAZO_CONTADORES == 5.0   # el valor real; abajo se acorta solo para no esperar 5 s
    monkeypatch.setattr(monitor_routes, "PLAZO_CONTADORES", 0.3)
    soltar = threading.Event()

    def colgada():
        soltar.wait(1.5)   # la BD «no responde»; si el plazo no actuara, la respuesta sería 200 tras esperar
        return [], None

    monkeypatch.setattr(contadores, "leer_ventana", colgada)
    try:
        r = client.get(RUTA, headers=sesiones["dueno"])   # (el cierre del bucle de pruebas espera al hilo)
        assert r.status_code == 503 and r.headers["cache-control"] == "no-store"
        assert "Timeout" not in r.text and "plazo" not in r.text.lower()
        o = client.get(RUTA, headers=sesiones["otro"])   # no-Dueño: sigue el 404 normal
        assert o.status_code == 404 and _sin_date(o) == _sin_date(client.get("/api/v1/no-existe"))
    finally:
        soltar.set()


def test_inv034_contadores_y_plataformas_en_paralelo(client, sesiones, externas, monkeypatch):
    async def lenta(_r):
        await asyncio.sleep(0.5)
        return httpx.Response(200, json=_respuesta_json(_r.url, _r) or {})

    for host in HOSTS_FIJOS:
        externas.por_host[host] = lenta

    def lectura_lenta():
        time.sleep(0.5)
        return [], None

    monkeypatch.setattr(contadores, "leer_ventana", lectura_lenta)
    t0 = time.monotonic()
    assert client.get(RUTA, headers=sesiones["dueno"]).status_code == 200
    assert time.monotonic() - t0 < 1.4   # secuencial serían >= 1.5 s (0.5 de contadores + 0.5 + 0.5 de Anthropic/Brevo)


# ==================== INV-035 ====================

def test_inv035_cache_60s_no_reconsulta(client, sesiones, externas, monkeypatch):
    reloj = [1000.0]
    monkeypatch.setattr(mp, "_reloj", lambda: reloj[0])
    primera = client.get(RUTA, headers=sesiones["dueno"])
    consultas = len(externas.peticiones)
    assert consultas > 0
    reloj[0] += 59
    segunda = client.get(RUTA, headers=sesiones["dueno"])
    assert len(externas.peticiones) == consultas
    assert segunda.json()["plataformas"] == primera.json()["plataformas"]   # `actualizado_en` es el de la consulta original
    reloj[0] += 2   # 61 s
    client.get(RUTA, headers=sesiones["dueno"])
    assert len(externas.peticiones) == 2 * consultas


def test_inv035_fallos_se_cachean_15s(client, sesiones, externas, monkeypatch):
    reloj = [1000.0]
    monkeypatch.setattr(mp, "_reloj", lambda: reloj[0])
    externas.por_host["api.vercel.com"] = lambda r: httpx.Response(500)
    client.get(RUTA, headers=sesiones["dueno"])
    assert len(externas.a("api.vercel.com")) == 1
    reloj[0] += 14
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert len(externas.a("api.vercel.com")) == 1
    assert _datos(r, "vercel")["estado"] == "no_disponible"
    reloj[0] += 2   # 16 s
    client.get(RUTA, headers=sesiones["dueno"])
    assert len(externas.a("api.vercel.com")) == 2
    # un acierto sí dura 60 s: Brevo (2 llamadas por consulta) no se vuelve a pedir a los 16 s
    assert len(externas.a("api.brevo.com")) == 2


def test_inv035_limite_20_por_minuto_responde_429(client, sesiones, externas):
    for _ in range(20):
        assert client.get(RUTA, headers=sesiones["dueno"]).status_code == 200
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert r.status_code == 429
    assert r.headers["cache-control"] == "no-store"


def test_inv035_405_del_dueno_cuenta_para_el_limite(client, sesiones, externas):
    for _ in range(20):
        assert client.post(RUTA, headers=sesiones["dueno"]).status_code == 405
    r = client.get(RUTA, headers=sesiones["dueno"])
    assert r.status_code == 429
    assert r.headers["cache-control"] == "no-store"


def test_inv035_no_dueno_sobre_el_limite_recibe_404_nunca_429(client, sesiones, externas):
    esperado = _sin_date(client.get("/api/v1/no-existe"))
    for _ in range(25):
        r = client.get(RUTA, headers=sesiones["otro"])
        assert r.status_code == 404 and _sin_date(r) == esperado
    # el cupo del Dueño no se gasta con las peticiones de otros
    assert client.get(RUTA, headers=sesiones["dueno"]).status_code == 200


def test_inv035_no_store_solo_en_respuestas_del_dueno(client, sesiones, externas, monkeypatch):
    assert client.get(RUTA, headers=sesiones["dueno"]).headers["cache-control"] == "no-store"          # 200
    assert client.post(RUTA, headers=sesiones["dueno"]).headers["cache-control"] == "no-store"         # 405
    monkeypatch.setattr(contadores, "leer_ventana", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert client.get(RUTA, headers=sesiones["dueno"]).headers["cache-control"] == "no-store"          # 503
    monitor_routes._limite.reset()
    for _ in range(20):
        client.post(RUTA, headers=sesiones["dueno"])
    assert client.get(RUTA, headers=sesiones["dueno"]).headers["cache-control"] == "no-store"          # 429
    # ningún 404 lo lleva
    monkeypatch.setattr(settings, "OWNER_EMAIL", "")
    for url, h in ((RUTA, sesiones["dueno"]), (RUTA, {}), ("/api/v1/monitor/no-existe", sesiones["dueno"]),
                   ("/api/v1/no-existe", {})):
        r = client.get(url, headers=h)
        assert r.status_code == 404 and "cache-control" not in r.headers


# ==================== contadores en la respuesta (CT-010) ====================

def test_contadores_agregados_por_dia(client, sesiones, externas):
    from datetime import timedelta
    hoy = contadores._hoy()
    ayer = hoy - timedelta(days=1)
    vieja = hoy - timedelta(days=45)   # fuera de la ventana de 30 días, pero cuenta para «desde»
    F = contadores._Memoria.filas
    F[(vieja, "claude_llamadas", "asistente")] = 1
    F[(ayer, "brevo_correos_enviados", "general")] = 2
    F[(hoy, "claude_llamadas", "asistente")] = 4
    F[(hoy, "claude_tokens_entrada", "asistente")] = 5200
    F[(hoy, "claude_tokens_salida", "asistente")] = 900
    F[(hoy, "claude_llamadas", "whatsapp")] = 2
    F[(hoy, "whatsapp_enviados", "general")] = 6
    F[(hoy, "whatsapp_recibidos", "general")] = 7
    F[(hoy, "purga", "general")] = 0   # la marca nunca aparece
    c = client.get(RUTA, headers=sesiones["dueno"]).json()["contadores"]
    assert c["desde"] == vieja.isoformat()
    assert [d["fecha"] for d in c["dias"]] == [ayer.isoformat(), hoy.isoformat()]
    assert c["dias"][0] == {
        "fecha": ayer.isoformat(),
        "claude": {"asistente": {"llamadas": 0, "tokens_entrada": 0, "tokens_salida": 0},
                   "whatsapp": {"llamadas": 0, "tokens_entrada": 0, "tokens_salida": 0}},
        "brevo_correos_enviados": 2, "whatsapp_mensajes": {"enviados": 0, "recibidos": 0}}
    assert c["dias"][1] == {
        "fecha": hoy.isoformat(),
        "claude": {"asistente": {"llamadas": 4, "tokens_entrada": 5200, "tokens_salida": 900},
                   "whatsapp": {"llamadas": 2, "tokens_entrada": 0, "tokens_salida": 0}},
        "brevo_correos_enviados": 0, "whatsapp_mensajes": {"enviados": 6, "recibidos": 7}}
    assert "purga" not in str(c)
