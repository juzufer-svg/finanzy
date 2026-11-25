"""
Pruebas de la suspensión, el cierre de sesiones y el último acceso (CHG-023, INV-056, INV-057, INV-061, BDD-ADMIN-USUARIOS).

Las funciones SQL reales (atomicidad, suspensiones simultáneas, 20 `registrar_acceso` a la vez) se prueban contra PostgreSQL
en `backend/sql/pruebas/11_comprobar_admin_usuarios.sql`. Aquí se prueba el comportamiento del backend: el modo demo del
modelo del panel reproduce la semántica de esas funciones y un cliente de Supabase simulado cubre lo que se escribe.
"""
import asyncio
import inspect
import json
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import auth_header
from app.api.routes import admin_usuarios as admin_routes
from app.api.sesion import SESION_INVALIDA
from app.core import security
from app.core.config import settings
from app.main import app
from app.models import admin_usuarios as admin_db
from app.models import auth_estado
from app.models import whatsapp as whatsapp_db
from app.models.user import UserDB
from app.core import supabase as supabase_mod

BASE = "/api/v1/admin"
DUENO, VICTIMA = "dueno@ejemplo.com", "victima@ejemplo.com"
PASS_VICTIMA = "ContrasenaVictima#1"
HASH_VICTIMA = security.get_password_hash(PASS_VICTIMA)
SQL = Path(__file__).resolve().parents[1] / "sql" / "2026-11-25_admin_usuarios.sql"
# Implementaciones reales (la fixture `users` las sustituye por un almacén en memoria; aquí se captura antes de cualquier parche)
_GET_SESSION_VERSION_REAL = UserDB.get_session_version
_UPDATE_PASSWORD_REAL = UserDB.update_password
MSG_SUSPENDIDA = "No fue posible iniciar sesión con esta cuenta. Contacta al administrador."


def _uid(correo: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, correo.lower()))


def _alta(store, correo, *, activo=True, suspendida=False, hashed="x", sv=0):
    store[correo.lower()] = {
        "id": _uid(correo), "email": correo, "full_name": "Nombre", "hashed_password": hashed, "is_active": activo,
        "suspendida": suspendida, "currency": "COP", "session_version": sv, "created_at": "2026-11-20T10:00:00",
        "ultimo_acceso": None,
    }
    return _uid(correo)


@pytest.fixture
def panel(users, monkeypatch):
    monkeypatch.setattr(settings, "OWNER_EMAIL", DUENO)
    monkeypatch.setattr(admin_db._Memoria, "usuarios", users)
    p = SimpleNamespace(store=users, id_dueno=_alta(users, DUENO), id_victima=_alta(users, VICTIMA, hashed=HASH_VICTIMA))
    p.dueno = auth_header(p.id_dueno)
    return p


def _token(uid: str, sv: int = 0) -> dict:
    return {"Authorization": "Bearer " + security.create_access_token({"sub": uid, "sv": sv})}


def _accion(client, panel, ruta):
    return client.post(f"{BASE}/usuarios/{panel.id_victima}/{ruta}", headers=panel.dueno)


def _login(client, correo=VICTIMA, password=PASS_VICTIMA):
    return client.post("/api/v1/auth/login", json={"email": correo, "password": password})


class ClienteFalso:
    """Cliente de Supabase simulado para `registrar_acceso`: guarda las llamadas y puede tardar, fallar o aplicar «1 vez/hora»."""

    def __init__(self):
        self.llamadas, self.hilos, self.espera, self.falla, self.respuesta = [], [], 0.0, None, True
        self.ahora, self.ultimo = 0.0, None   # reloj de la «BD» (segundos) y último acceso escrito
        self.por_hora = False

    def rpc(self, nombre, args):
        cliente = self

        class Ejecucion:
            def execute(self_):
                cliente.llamadas.append((nombre, dict(args)))
                cliente.hilos.append(threading.current_thread().name)
                time.sleep(cliente.espera)
                if cliente.falla is not None:
                    raise cliente.falla
                if cliente.por_hora:
                    escribe = cliente.ultimo is None or cliente.ultimo < cliente.ahora - 3600
                    if escribe:
                        cliente.ultimo = cliente.ahora
                    return SimpleNamespace(data=escribe)
                return SimpleNamespace(data=cliente.respuesta)
        return Ejecucion()


@pytest.fixture
def acceso(monkeypatch):
    falso = ClienteFalso()
    monkeypatch.setattr(UserDB, "_is_supabase_available", staticmethod(lambda: True))
    monkeypatch.setattr(auth_estado, "cliente_estado", lambda: falso)
    return falso


def _consulta_falsa(filas, registro):
    """Consulta encadenable de Supabase que registra cada llamada y devuelve `filas` al ejecutar."""
    class Consulta:
        def __getattr__(self, nombre):
            def llamar(*a, **k):
                registro.append((nombre, a))
                return self
            return llamar

        def execute(self):
            if isinstance(filas, BaseException):
                raise filas
            return SimpleNamespace(data=filas)
    return Consulta()


def _supabase_falso(monkeypatch, filas, registro):
    monkeypatch.setattr(UserDB, "_is_supabase_available", staticmethod(lambda: True))
    cliente = SimpleNamespace(table=lambda nombre: (registro.append(("table", (nombre,))), _consulta_falsa(filas, registro))[1])
    monkeypatch.setattr(supabase_mod.SupabaseDB, "get_client", staticmethod(lambda: cliente))


# ==================== INV-056 ====================

def test_inv056_login_de_suspendida_con_contrasena_correcta_responde_403_generico(client, panel):
    panel.store[VICTIMA]["suspendida"] = True
    r = _login(client)
    assert r.status_code == 403 and r.json() == {"detail": MSG_SUSPENDIDA}
    assert "no está" not in r.text and "suspend" not in r.text.lower()


def test_inv056_login_de_suspendida_con_contrasena_incorrecta_responde_401_igual_que_siempre(client, panel):
    panel.store[VICTIMA]["suspendida"] = True
    r = _login(client, password="incorrecta-1")
    inexistente = _login(client, correo="nadie@ejemplo.com", password="incorrecta-1")
    assert r.status_code == 401 and r.json() == {"detail": "Credenciales inválidas"} == inexistente.json()
    assert auth_estado._Memoria.intentos[auth_estado.huella_correo(VICTIMA)]["fallos"] == 1   # cuenta como fallo


def test_inv056_el_login_de_suspendida_no_emite_token_ni_codigo(client, panel, sent_emails):
    panel.store[VICTIMA]["suspendida"] = True
    r = _login(client)
    assert r.status_code == 403 and "access_token" not in r.text and "token" not in r.text.lower()
    assert sent_emails == [] and auth_estado._Memoria.codigos == {}
    assert auth_estado.huella_correo(VICTIMA) not in auth_estado._Memoria.intentos   # el acierto reinició la serie, no cuenta


def test_inv056_sesion_abierta_de_suspendida_recibe_401(client, panel):
    viejo = _token(panel.id_victima)
    assert client.get("/api/v1/users/me", headers=viejo).status_code == 200
    assert _accion(client, panel, "suspender").status_code == 200
    r = client.get("/api/v1/users/me", headers=viejo)
    assert r.status_code == 401 and r.json() == {"detail": SESION_INVALIDA}
    # aunque el token fuera de la versión nueva, una suspendida no tiene sesión
    assert client.get("/api/v1/users/me", headers=_token(panel.id_victima, 1)).status_code == 401


def test_inv056_suspender_marca_suspendida_y_sube_session_version_juntas(client, panel):
    panel.store[VICTIMA]["session_version"] = 5
    assert _accion(client, panel, "suspender").status_code == 200
    assert panel.store[VICTIMA]["suspendida"] is True and panel.store[VICTIMA]["session_version"] == 6
    sql = SQL.read_text(encoding="utf-8")
    funcion = sql.split("create or replace function public.admin_suspender_usuario")[1].split("$$;")[0]
    assert "set suspendida = true, session_version = session_version + 1 where id = p_id" in funcion   # una sola sentencia
    assert "for update" in funcion and "admin_registrar_auditoria('suspender'" in funcion


def test_inv056_usuario_de_sesion_lee_suspendida_en_la_misma_consulta(monkeypatch):
    registro = []
    _supabase_falso(monkeypatch, [{"session_version": 3, "is_active": True, "suspendida": False}], registro)
    assert asyncio.run(UserDB.get_session_version("u1")) == 3
    selects = [a[0] for n, a in registro if n == "select"]
    assert selects == ["session_version,is_active,suspendida"]   # una sola consulta, con la columna
    assert [n for n, _ in registro].count("execute") == 0 and [a for n, a in registro if n == "table"] == [("users",)]
    registro.clear()
    _supabase_falso(monkeypatch, [{"session_version": 3, "is_active": True, "suspendida": True}], registro)
    assert asyncio.run(UserDB.get_session_version("u1")) is None
    _supabase_falso(monkeypatch, [{"session_version": 3, "is_active": False, "suspendida": False}], registro)
    assert asyncio.run(UserDB.get_session_version("u1")) is None


def test_inv056_bd_caida_al_verificar_suspendida_responde_503_no_401(client, panel, monkeypatch):
    # la fixture `users` reemplaza get_session_version: se restaura la real con un Supabase que falla
    monkeypatch.setattr(UserDB, "get_session_version", staticmethod(_GET_SESSION_VERSION_REAL))
    _supabase_falso(monkeypatch, RuntimeError("Supabase caído con datos@ejemplo.com"), [])
    r = client.get("/api/v1/users/me", headers=_token(panel.id_victima))
    assert r.status_code == 503 and "datos@ejemplo.com" not in r.text


def test_inv056_verify_email_no_emite_sesion_a_suspendida(client, panel):
    """A nivel de función: por el flujo normal casi no se alcanza (una suspendida está activa y no recibe códigos)."""
    panel.store[VICTIMA]["suspendida"] = True
    asyncio.run(auth_estado.codigo_emitir(VICTIMA, "verify", "123456"))
    r = client.post("/api/v1/auth/verify-email", json={"email": VICTIMA, "code": "123456"})
    assert r.status_code == 403 and r.json() == {"detail": MSG_SUSPENDIDA} and "access_token" not in r.text


def test_inv056_reset_password_no_reactiva_a_la_suspendida(client, panel, monkeypatch):
    panel.store[VICTIMA]["suspendida"] = True
    asyncio.run(auth_estado.codigo_emitir(VICTIMA, "reset", "654321"))
    r = client.post("/api/v1/auth/reset-password", json={"email": VICTIMA, "code": "654321", "new_password": "NuevaClave#2026"})
    assert r.status_code == 200 and panel.store[VICTIMA]["suspendida"] is True
    assert _login(client, password="NuevaClave#2026").status_code == 403   # sigue suspendida
    # la actualización real de la contraseña nunca escribe `suspendida`
    escrituras = []
    sentencias = [{"session_version": 1}]

    class Consulta:
        def __getattr__(self, nombre):
            def llamar(*a, **k):
                if nombre == "update":
                    escrituras.append(a[0])
                return self
            return llamar

        def execute(self):
            return SimpleNamespace(data=sentencias)
    monkeypatch.setattr(UserDB, "_is_supabase_available", staticmethod(lambda: True))
    monkeypatch.setattr(supabase_mod.SupabaseDB, "get_client", staticmethod(lambda: SimpleNamespace(table=lambda _n: Consulta())))
    monkeypatch.setattr(UserDB, "update_password", staticmethod(_UPDATE_PASSWORD_REAL))
    asyncio.run(UserDB.update_password(VICTIMA, "OtraClave#2026"))
    assert escrituras and all("suspendida" not in e for e in escrituras)


def test_inv056_reactivar_permite_login_pero_no_revive_tokens_viejos(client, panel):
    viejo = _token(panel.id_victima)
    assert _accion(client, panel, "suspender").status_code == 200
    assert _login(client).status_code == 403
    assert _accion(client, panel, "reactivar").json()["estado"] == "activa"
    ok = _login(client)
    assert ok.status_code == 200 and ok.json()["access_token"]
    assert client.get("/api/v1/users/me", headers=viejo).status_code == 401   # su `sv` ya no coincide
    assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + ok.json()["access_token"]}).status_code == 200


def test_inv056_suspender_desconecta_whatsapp(client, panel):
    whatsapp_db._Memoria.enlaces[panel.id_victima] = "573001112233"
    assert _accion(client, panel, "suspender").status_code == 200
    assert panel.id_victima not in whatsapp_db._Memoria.enlaces
    assert "whatsapp_enlaces" in SQL.read_text(encoding="utf-8").split("admin_suspender_usuario")[1].split("$$;")[0]


def test_inv056_suspender_cuenta_pendiente_responde_409(client, panel):
    panel.store[VICTIMA]["is_active"] = False
    r = _accion(client, panel, "suspender")
    assert r.status_code == 409 and r.json() == {"detail": "La cuenta aún no está verificada"}
    assert panel.store[VICTIMA]["suspendida"] is False and admin_db._Memoria.auditoria == []


def test_inv056_suspender_dos_veces_responde_409_y_audita_una_sola_vez(client, panel):
    assert _accion(client, panel, "suspender").status_code == 200
    r = _accion(client, panel, "suspender")
    assert r.status_code == 409 and r.json() == {"detail": "La cuenta ya está suspendida"}
    assert panel.store[VICTIMA]["session_version"] == 1 and len(admin_db._Memoria.auditoria) == 1


def test_inv056_la_limpieza_de_cuentas_sin_verificar_no_toca_a_las_suspendidas(monkeypatch):
    registro = []
    _supabase_falso(monkeypatch, [], registro)
    asyncio.run(UserDB.delete_unverified_expired())
    assert ("eq", ("is_active", False)) in registro   # solo filas con is_active = false; una suspendida es activa
    sql = SQL.read_text(encoding="utf-8")
    assert "suspendida boolean not null default false" in sql
    funcion = sql.split("create or replace function public.admin_suspender_usuario")[1].split("$$;")[0]
    assert "is_active" not in funcion.split("update public.users")[1].split("where")[0]   # suspender no toca is_active


# ==================== INV-057 ====================

def test_inv057_cerrar_sesiones_sube_session_version_en_uno(client, panel):
    panel.store[VICTIMA]["session_version"] = 3
    r = _accion(client, panel, "cerrar-sesiones")
    assert r.status_code == 200 and panel.store[VICTIMA]["session_version"] == 4
    # sin «leer y escribir» en Python: la ruta no calcula la versión; la sentencia SQL es atómica
    assert "session_version" not in inspect.getsource(admin_routes._ejecutar_accion)
    funcion = SQL.read_text(encoding="utf-8").split("create or replace function public.admin_cerrar_sesiones_usuario")[1].split("$$;")[0]
    assert "set session_version = session_version + 1 where id = p_id" in funcion


def test_inv057_el_token_anterior_recibe_401_y_el_login_nuevo_funciona(client, panel):
    panel.store[VICTIMA]["session_version"] = 3
    viejo = _token(panel.id_victima, 3)
    assert client.get("/api/v1/users/me", headers=viejo).status_code == 200
    assert _accion(client, panel, "cerrar-sesiones").status_code == 200
    assert client.get("/api/v1/users/me", headers=viejo).status_code == 401
    nuevo = _login(client)
    assert nuevo.status_code == 200
    assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + nuevo.json()["access_token"]}).status_code == 200


def test_inv057_cerrar_sesiones_desconecta_whatsapp(client, panel):
    whatsapp_db._Memoria.enlaces[panel.id_victima] = "573001112233"
    assert _accion(client, panel, "cerrar-sesiones").status_code == 200
    assert whatsapp_db._Memoria.enlaces == {}


def test_inv057_no_cambia_estado_ni_contrasena(client, panel):
    antes = dict(panel.store[VICTIMA])
    assert _accion(client, panel, "cerrar-sesiones").status_code == 200
    despues = dict(panel.store[VICTIMA])
    assert despues.pop("session_version") == antes.pop("session_version") + 1
    assert despues == antes   # contraseña, is_active, suspendida y datos intactos


# ==================== INV-061 ====================

def test_inv061_login_registra_ultimo_acceso(client, panel, acceso):
    r = _login(client)
    assert r.status_code == 200
    assert acceso.llamadas == [("registrar_acceso", {"p_id": panel.id_victima})]


def test_inv061_verify_email_tambien_registra(client, panel, acceso):
    panel.store[VICTIMA]["is_active"] = False
    asyncio.run(auth_estado.codigo_emitir(VICTIMA, "verify", "123456"))
    r = client.post("/api/v1/auth/verify-email", json={"email": VICTIMA, "code": "123456"})
    assert r.status_code == 200 and r.json()["access_token"]
    assert acceso.llamadas == [("registrar_acceso", {"p_id": panel.id_victima})]


def test_inv061_como_maximo_una_vez_por_hora(client, panel, acceso):
    """La barrera es la sentencia condicional de la BD (`registrar_acceso`, probada en PostgreSQL): aquí se comprueba que el
    backend la llama en cada inicio de sesión sin guardar nada por su cuenta y que la «BD» escribe una sola vez por hora."""
    acceso.por_hora = True
    assert _login(client).status_code == 200 and _login(client).status_code == 200
    assert len(acceso.llamadas) == 2 and acceso.ultimo == 0.0   # escribió una sola vez
    acceso.ahora = 3601.0
    assert _login(client).status_code == 200
    assert acceso.ultimo == 3601.0
    sql = SQL.read_text(encoding="utf-8").split("create or replace function public.registrar_acceso")[1].split("$$;")[0]
    assert "ultimo_acceso is null or ultimo_acceso < now() - interval '1 hour'" in sql and "now()" in sql
    assert "p_ahora" not in sql   # el reloj es el de la BD


def test_inv061_un_fallo_al_registrar_no_rompe_el_login(client, panel, acceso, capsys, caplog):
    acceso.falla = RuntimeError(f"fallo con {VICTIMA} y {PASS_VICTIMA}")
    r = _login(client)
    assert r.status_code == 200 and r.json()["access_token"]
    salida = capsys.readouterr()
    todo = salida.out + salida.err + caplog.text
    assert "último acceso" in todo or "registrar_acceso" in todo
    assert VICTIMA not in todo and PASS_VICTIMA not in todo and "fallo con" not in todo


def test_inv061_se_registra_en_segundo_plano_tras_responder_el_login(panel, acceso):
    eventos = []
    original = acceso.rpc

    def rpc(nombre, args):
        eventos.append("escritura")
        return original(nombre, args)
    acceso.rpc = rpc
    cuerpo = json.dumps({"email": VICTIMA, "password": PASS_VICTIMA}).encode()
    entregado = []

    async def receive():
        if entregado:
            await asyncio.sleep(3600)
        entregado.append(1)
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.body" and not msg.get("more_body"):
            eventos.append("respuesta")
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": "/api/v1/auth/login", "raw_path": b"/api/v1/auth/login", "query_string": b"", "root_path": "",
             "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(cuerpo)).encode())],
             "client": ("127.0.0.1", 5), "server": ("t", 80)}
    acceso.espera = 0.2
    asyncio.run(asyncio.wait_for(app(scope, receive, send), timeout=20))
    assert eventos == ["respuesta", "escritura"]   # la respuesta sale ANTES de escribir


def test_inv061_registrar_acceso_tiene_plazo_propio_de_2s_y_no_afecta_la_respuesta(client, panel, acceso, monkeypatch):
    from app.models import user as user_mod
    assert user_mod.PLAZO_REGISTRAR_ACCESO_SEG == 2.0
    monkeypatch.setattr(user_mod, "PLAZO_REGISTRAR_ACCESO_SEG", 0.2)   # se acorta para no esperar 2 s
    acceso.espera = 1.0
    inicio = time.monotonic()
    assert asyncio.run(UserDB.registrar_acceso(panel.id_victima)) is False
    assert time.monotonic() - inicio < 0.9   # no espera a la BD lenta
    assert "auth-estado" in acceso.hilos[0]   # fuera del event loop, en el ejecutor propio
    acceso.espera, acceso.llamadas = 0.0, []
    r = _login(client)   # el login no depende del resultado
    assert r.status_code == 200 and r.json()["access_token"]


def test_inv061_no_registra_con_contrasena_incorrecta_ni_con_cuenta_suspendida(client, panel, acceso):
    assert _login(client, password="incorrecta-1").status_code == 401
    panel.store[VICTIMA]["suspendida"] = True
    assert _login(client).status_code == 403
    assert _login(client, correo="nadie@ejemplo.com").status_code == 401
    assert acceso.llamadas == []


def test_inv061_el_aviso_de_fallo_no_lleva_datos(panel, acceso, capsys):
    acceso.falla = ValueError(f"detalle con {VICTIMA}")
    assert asyncio.run(UserDB.registrar_acceso(panel.id_victima)) is False
    acceso.falla = None
    acceso.respuesta = {"rara": "respuesta"}   # respuesta rara: no escribe y no rompe
    assert asyncio.run(UserDB.registrar_acceso(panel.id_victima)) is False
    salida = capsys.readouterr()
    assert "ValueError" in salida.out and VICTIMA not in salida.out + salida.err and panel.id_victima not in salida.out
