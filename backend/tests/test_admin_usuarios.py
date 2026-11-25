"""
Pruebas del panel de administración de usuarios del Dueño (CHG-023, CT-013, ADR-012, UC-017, BDD-ADMIN-USUARIOS).

Cubre INV-053 (acceso), INV-054 (autoprotección), INV-055 (privacidad), INV-058 (eliminar), INV-059 (auditoría) e INV-060
(límites, paginación, búsqueda). La suspensión, el cierre de sesiones y el último acceso están en `test_admin_suspension.py`;
las funciones SQL reales, en `backend/sql/pruebas/11_comprobar_admin_usuarios.sql`.

La mayoría de las pruebas usan el modo demo del modelo (misma semántica que las funciones SQL) sobre el almacén `users`;
las de plazos, una sola llamada y respuestas hostiles usan el modo «bd» con una función RPC simulada.
"""
import asyncio
import copy
import hmac
import json
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import auth_header
from app.api import dueno as dueno_mod
from app.api.routes import admin_usuarios as admin_routes
from app.core import security
from app.core.config import settings
from app.main import app
from app.models import admin_usuarios as admin_db
from app.models import auth_estado, demo_db
from app.models import whatsapp as whatsapp_db
from app.models.auth_estado import EstadoNoDisponible
from app.models.user import UserDB

BASE = "/api/v1/admin"
DUENO = "dueno@ejemplo.com"
OTRO = "otra@ejemplo.com"
VICTIMA = "victima@ejemplo.com"
PASS_DUENO = "ContrasenaDueno#Secreta-77"
HASH_DUENO = security.get_password_hash(PASS_DUENO)   # una sola vez: bcrypt tarda ~0,3 s
SQL = Path(__file__).resolve().parents[1] / "sql" / "2026-11-25_admin_usuarios.sql"


# ==================== ayudas ====================

def _uid(correo: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, correo.lower()))


def _alta(store: dict, correo: str, *, activo=True, suspendida=False, nombre="Nombre", creado="2026-11-20T10:00:00",
          hashed="x", sv=0, clave=None) -> str:
    store[clave or correo.lower()] = {
        "id": _uid(correo), "email": correo, "full_name": nombre, "hashed_password": hashed, "is_active": activo,
        "suspendida": suspendida, "currency": "COP", "session_version": sv, "created_at": creado, "ultimo_acceso": None,
    }
    return _uid(correo)


@pytest.fixture
def panel(users, monkeypatch):
    """OWNER_EMAIL con mayúsculas y espacios a propósito; el Dueño, otra persona y una víctima con sesión válida."""
    monkeypatch.setattr(settings, "OWNER_EMAIL", "  DUENO@Ejemplo.com ")
    monkeypatch.setattr(admin_db._Memoria, "usuarios", users)
    p = SimpleNamespace(store=users)
    p.id_dueno = _alta(users, DUENO, hashed=HASH_DUENO, nombre="El Dueño")
    p.id_otro = _alta(users, OTRO, creado="2026-11-21T10:00:00")
    p.id_victima = _alta(users, VICTIMA, nombre="Víctima Pérez", creado="2026-11-22T10:00:00")
    p.dueno, p.otro, p.victima = auth_header(p.id_dueno), auth_header(p.id_otro), auth_header(p.id_victima)
    return p


def _pet(client, metodo, ruta, cab=None, **kw):
    return client.request(metodo, BASE + ruta, headers=cab or {}, **kw)


def _eliminar(client, panel, uid, correo=VICTIMA, contrasena=PASS_DUENO, cab=None, **kw):
    cuerpo = {"confirmar_correo": correo, "contrasena_dueno": contrasena}
    return _pet(client, "DELETE", f"/usuarios/{uid}", cab or panel.dueno, json=cuerpo, **kw)


def _sin_date(resp) -> tuple:
    return resp.status_code, resp.content, sorted((k.lower(), v) for k, v in resp.headers.items() if k.lower() != "date")


def _auditoria(client, panel) -> list:
    r = _pet(client, "GET", "/auditoria", panel.dueno)
    assert r.status_code == 200
    return r.json()["registros"]


RUTAS = [
    ("GET", "/usuarios"), ("GET", "/usuarios/{id}"), ("POST", "/usuarios/{id}/suspender"),
    ("POST", "/usuarios/{id}/reactivar"), ("POST", "/usuarios/{id}/cerrar-sesiones"),
    ("DELETE", "/usuarios/{id}"), ("GET", "/auditoria"),
]


@pytest.fixture
def bd(panel, monkeypatch):
    """Modo «bd» del modelo con una función RPC simulada: `respuestas[nombre]` es el valor, una excepción o una función."""
    estado = SimpleNamespace(llamadas=[], respuestas={})
    monkeypatch.setattr(admin_db, "_modo", lambda: "bd")

    def rpc(nombre, args):
        estado.llamadas.append((nombre, dict(args)))
        r = estado.respuestas.get(nombre)
        if isinstance(r, BaseException):
            raise r
        return r(args) if callable(r) else r
    monkeypatch.setattr(admin_db, "_rpc", rpc)
    return estado


def _fila_bd(**extra):
    base = {"id": _uid("fila@ejemplo.com"), "correo": "fila@ejemplo.com", "nombre": "Fila", "estado": "activa",
            "moneda": "COP", "registrado_en": "2026-11-20T10:00:00Z", "ultimo_acceso": None, "uso": {"transacciones": 3}}
    base.update(extra)
    return base


# ==================== INV-053 ====================

@pytest.mark.parametrize("metodo,ruta", RUTAS)
def test_inv053_no_dueno_recibe_404_identico_a_ruta_inexistente(client, panel, metodo, ruta):
    url = ruta.format(id=panel.id_victima)
    esperado = client.get("/api/v1/no-existe", headers=panel.otro)
    assert esperado.status_code == 404 and esperado.json() == {"detail": "Not Found"}
    r = _pet(client, metodo, url, panel.otro)
    assert _sin_date(r) == _sin_date(esperado)
    assert "cache-control" not in r.headers and "allow" not in r.headers


def test_inv053_sin_sesion_recibe_404(client, panel):
    for metodo, ruta in RUTAS:
        r = _pet(client, metodo, ruta.format(id=panel.id_victima))
        assert _sin_date(r) == _sin_date(client.get("/api/v1/no-existe"))
    assert _sin_date(_pet(client, "GET", "/usuarios", {"Authorization": "Bearer basura"})) == _sin_date(client.get("/api/v1/no-existe"))


@pytest.mark.parametrize("valor", ["", "   "])
def test_inv053_sin_owner_email_responde_404_y_no_mira_la_sesion(client, panel, monkeypatch, valor):
    vistos = []

    async def espia(user_id):
        vistos.append(user_id)
        return {"email": DUENO}

    async def espia_version(user_id):
        vistos.append(user_id)
        return 0

    monkeypatch.setattr(settings, "OWNER_EMAIL", valor)
    monkeypatch.setattr(UserDB, "get_by_id", staticmethod(espia))
    monkeypatch.setattr(UserDB, "get_session_version", staticmethod(espia_version))
    for metodo, ruta in RUTAS:
        r = _pet(client, metodo, ruta.format(id=panel.id_victima), panel.dueno)
        assert _sin_date(r) == _sin_date(client.get("/api/v1/no-existe"))
    assert vistos == []


def test_inv053_bd_caida_al_autorizar_responde_404(client, panel, monkeypatch):
    async def falla(_user_id):
        raise RuntimeError("Supabase caído")
    monkeypatch.setattr(UserDB, "get_session_version", staticmethod(falla))
    for cab in (panel.dueno, panel.otro):
        r = _pet(client, "GET", "/usuarios", cab)
        assert r.status_code == 404   # no 503
        assert _sin_date(r) == _sin_date(client.get("/api/v1/no-existe"))
        assert "cache-control" not in r.headers


def test_inv053_sesion_vieja_o_cuenta_suspendida_recibe_404(client, panel):
    esperado = _sin_date(client.get("/api/v1/no-existe"))
    panel.store[DUENO]["session_version"] = 1   # el token no trae «sv»: cuenta como 0 y ya no coincide
    assert _sin_date(_pet(client, "GET", "/usuarios", panel.dueno)) == esperado
    panel.store[DUENO]["session_version"] = 0
    assert _pet(client, "GET", "/usuarios", panel.dueno).status_code == 200
    panel.store[DUENO]["suspendida"] = True
    assert _sin_date(_pet(client, "GET", "/usuarios", panel.dueno)) == esperado
    panel.store[DUENO]["suspendida"] = False
    panel.store[DUENO]["is_active"] = False
    assert _sin_date(_pet(client, "GET", "/usuarios", panel.dueno)) == esperado


def test_inv053_no_dueno_con_parametros_invalidos_recibe_404_y_no_422(client, panel):
    esperado = _sin_date(client.get("/api/v1/no-existe", headers=panel.otro))
    casos = [("GET", "/usuarios?q=" + "x" * 61, None), ("GET", "/usuarios?pagina=abc", None), ("GET", "/usuarios?pagina=0", None),
             ("GET", "/usuarios?pagina=1&pagina=2", None), ("GET", "/usuarios/no-es-uuid", None),
             ("POST", "/usuarios/no-es-uuid/suspender", None), ("DELETE", f"/usuarios/{panel.id_victima}", None),
             ("DELETE", f"/usuarios/{panel.id_victima}", {"json": {"otra": 1}}),
             ("DELETE", f"/usuarios/{panel.id_victima}", {"content": b"x" * 5000}),
             ("GET", "/auditoria?pagina=-4", None)]
    for metodo, ruta, kw in casos:
        r = _pet(client, metodo, ruta, panel.otro, **(kw or {}))
        assert r.status_code == 404 and _sin_date(r) == esperado, (metodo, ruta)


@pytest.mark.parametrize("metodo", ["PUT", "PATCH", "HEAD", "TRACE", "PROPFIND", "FOO", "OPTIONS"])
def test_inv053_no_dueno_con_cualquier_metodo_recibe_404(client, panel, metodo):
    """Sin Origin ni cabeceras de preflight, OPTIONS no lo atiende el middleware CORS: llega al despachador."""
    for ruta in ("/usuarios", f"/usuarios/{panel.id_victima}", f"/usuarios/{panel.id_victima}/suspender", "/auditoria"):
        for cab in ({}, panel.otro):
            r = _pet(client, metodo, ruta, cab)
            esperado = client.request(metodo, "/api/v1/no-existe", headers=cab)
            assert r.status_code == 404 and _sin_date(r) == _sin_date(esperado), (metodo, ruta)
            assert "cache-control" not in r.headers and "allow" not in r.headers


@pytest.mark.parametrize("metodo,ruta,allow", [
    ("PUT", "/usuarios", "GET"), ("PATCH", "/usuarios/{id}", "GET, DELETE"), ("HEAD", "/usuarios", "GET"),
    ("GET", "/usuarios/{id}/suspender", "POST"), ("DELETE", "/usuarios", "GET"), ("POST", "/auditoria", "GET"),
    ("TRACE", "/usuarios/{id}/reactivar", "POST"), ("FOO", "/usuarios/{id}/cerrar-sesiones", "POST"), ("OPTIONS", "/usuarios", "GET"),
])
def test_inv053_dueno_con_metodo_no_permitido_recibe_405_con_allow_y_no_store(client, panel, metodo, ruta, allow):
    r = _pet(client, metodo, ruta.format(id=panel.id_victima), panel.dueno)
    assert r.status_code == 405
    assert r.headers["allow"] == allow and r.headers["cache-control"] == "no-store"
    assert panel.store[VICTIMA]["session_version"] == 0 and not panel.store[VICTIMA]["suspendida"]


def test_inv053_subruta_inexistente_responde_404_normal_a_todos(client, panel):
    esperado = _sin_date(client.get("/api/v1/no-existe"))
    for ruta in ("/no-existe", "/usuarios/x/y/z", f"/usuarios/{panel.id_victima}/borrar", "/usuarios//suspender", "/auditoria/7"):
        for cab in ({}, panel.otro, panel.dueno):
            for metodo in ("GET", "POST", "DELETE"):
                r = _pet(client, metodo, ruta, cab)
                assert _sin_date(r) == esperado, (metodo, ruta)


def test_inv053_barra_final_es_404_normal(client, panel):
    esperado = _sin_date(client.get("/api/v1/no-existe"))
    for ruta in ("/usuarios/", "/auditoria/", "/", f"/usuarios/{panel.id_victima}/", f"/usuarios/{panel.id_victima}/suspender/"):
        for cab in ({}, panel.otro, panel.dueno):
            r = _pet(client, "GET", ruta, cab)
            assert _sin_date(r) == esperado, ruta
    assert _sin_date(client.get(BASE, headers=panel.dueno)) == esperado


def test_inv053_404_de_subruta_inexistente_del_dueno_no_lleva_no_store(client, panel):
    r = _pet(client, "GET", "/no-existe", panel.dueno)
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"} and "cache-control" not in r.headers
    # ...y no cuenta para el límite
    for _ in range(70):
        assert _pet(client, "GET", "/no-existe", panel.dueno).status_code == 404
    assert _pet(client, "GET", "/usuarios", panel.dueno).status_code == 200
    # su 404 «Usuario no encontrado» sobre una ruta existente SÍ lleva no-store
    inexistente = _pet(client, "GET", f"/usuarios/{uuid.uuid4()}", panel.dueno)
    assert inexistente.status_code == 404 and inexistente.json() == {"detail": "Usuario no encontrado"}
    assert inexistente.headers["cache-control"] == "no-store"


def test_inv053_reutiliza_es_correo_dueno_con_compare_digest(client, panel, monkeypatch):
    llamadas = []

    class HmacEspia:
        @staticmethod
        def compare_digest(a, b):
            llamadas.append((a, b))
            return hmac.compare_digest(a, b)

    monkeypatch.setattr(dueno_mod, "hmac", HmacEspia)
    assert _pet(client, "GET", "/auditoria", panel.dueno).status_code == 200
    assert (b"dueno@ejemplo.com", b"dueno@ejemplo.com") in llamadas
    llamadas.clear()
    assert _pet(client, "GET", "/usuarios", panel.otro).status_code == 404
    assert llamadas == [(b"otra@ejemplo.com", b"dueno@ejemplo.com")]
    assert admin_routes.es_correo_dueno is dueno_mod.es_correo_dueno


def test_inv053_429_y_503_solo_despues_de_confirmar_al_dueno(client, panel, monkeypatch):
    async def falla(*_a, **_k):
        raise EstadoNoDisponible("simulado")
    monkeypatch.setattr(admin_db, "listar", falla)
    esperado = _sin_date(client.get("/api/v1/no-existe"))
    r = _pet(client, "GET", "/usuarios", panel.dueno)
    assert r.status_code == 503 and r.headers["cache-control"] == "no-store"
    assert _sin_date(_pet(client, "GET", "/usuarios", panel.otro)) == esperado
    for _ in range(120):   # el no-Dueño nunca ve 429
        assert _pet(client, "GET", "/usuarios", panel.otro).status_code == 404
    admin_routes._limite.reset()
    for _ in range(60):
        _pet(client, "GET", "/usuarios", panel.dueno)
    r = _pet(client, "GET", "/usuarios", panel.dueno)
    assert r.status_code == 429 and r.headers["cache-control"] == "no-store"
    assert _sin_date(_pet(client, "GET", "/usuarios", panel.otro)) == esperado


def test_inv053_no_store_solo_en_respuestas_al_dueno(client, panel):
    for metodo, ruta in RUTAS[:2] + RUTAS[-1:]:
        assert _pet(client, metodo, ruta.format(id=panel.id_victima), panel.dueno).headers["cache-control"] == "no-store"
    assert _pet(client, "POST", f"/usuarios/{panel.id_victima}/cerrar-sesiones", panel.dueno).headers["cache-control"] == "no-store"
    assert _eliminar(client, panel, panel.id_victima).headers["cache-control"] == "no-store"   # 204
    assert _pet(client, "PUT", "/usuarios", panel.dueno).headers["cache-control"] == "no-store"
    assert _pet(client, "GET", "/usuarios/abc", panel.dueno).headers["cache-control"] == "no-store"   # 422
    for metodo, ruta in RUTAS:
        assert "cache-control" not in _pet(client, metodo, ruta.format(id=panel.id_otro), panel.otro).headers
        assert "cache-control" not in _pet(client, metodo, ruta.format(id=panel.id_otro)).headers


def test_inv053_los_get_no_escriben_en_la_bd(client, panel, monkeypatch):
    antes = copy.deepcopy(panel.store)
    escrituras = []
    for nombre in ("suspender", "reactivar", "cerrar_sesiones", "eliminar"):
        async def espia(*a, _n=nombre, **k):
            escrituras.append(_n)
            return "ok"
        monkeypatch.setattr(admin_db, nombre, espia)
    for ruta in ("/usuarios", f"/usuarios/{panel.id_victima}", "/auditoria", "/usuarios?q=ana&pagina=1"):
        assert _pet(client, "GET", ruta, panel.dueno).status_code == 200
    assert escrituras == [] and panel.store == antes and admin_db._Memoria.auditoria == []


# ==================== INV-054 ====================

def _intacto(panel, antes):
    assert panel.store == antes
    assert admin_db._Memoria.auditoria == []


def test_inv054_el_dueno_no_puede_suspenderse(client, panel):
    antes = copy.deepcopy(panel.store)
    r = _pet(client, "POST", f"/usuarios/{panel.id_dueno}/suspender", panel.dueno)
    assert r.status_code == 409 and r.json() == {"detail": "No puedes hacerlo sobre tu propia cuenta"}
    _intacto(panel, antes)


def test_inv054_el_dueno_no_puede_eliminarse(client, panel):
    antes = copy.deepcopy(panel.store)
    r = _eliminar(client, panel, panel.id_dueno, correo=DUENO)
    assert r.status_code == 409
    assert auth_estado._Memoria.intentos == {}   # ni siquiera se comprobó la contraseña
    _intacto(panel, antes)


def test_inv054_el_dueno_no_puede_cerrar_sus_propias_sesiones(client, panel):
    antes = copy.deepcopy(panel.store)
    assert _pet(client, "POST", f"/usuarios/{panel.id_dueno}/cerrar-sesiones", panel.dueno).status_code == 409
    _intacto(panel, antes)


def test_inv054_proteccion_por_correo_aunque_el_id_sea_otro(client, panel):
    """Otra fila con el correo del Dueño (otro id, mayúsculas y espacios): sigue siendo el Dueño."""
    otro_id = _alta(panel.store, " DUENO@ejemplo.com ", clave="alias")
    antes = copy.deepcopy(panel.store)
    for ruta in ("suspender", "cerrar-sesiones"):
        assert _pet(client, "POST", f"/usuarios/{otro_id}/{ruta}", panel.dueno).status_code == 409
    assert _eliminar(client, panel, otro_id, correo=DUENO).status_code == 409
    _intacto(panel, antes)


def test_inv054_la_lista_no_expone_el_id_de_la_cuenta_del_dueno(client, panel):
    r = _pet(client, "GET", "/usuarios", panel.dueno)
    filas = {f["correo"]: f for f in r.json()["usuarios"]}
    assert filas[DUENO]["id"] is None and filas[DUENO]["es_dueno"] is True
    assert filas[OTRO]["id"] == panel.id_otro and filas[OTRO]["es_dueno"] is False
    assert panel.id_dueno not in r.text
    detalle = _pet(client, "GET", f"/usuarios/{panel.id_dueno}", panel.dueno)
    assert detalle.json()["id"] is None and panel.id_dueno not in detalle.text


def test_inv054_el_rechazo_no_escribe_ni_audita(client, panel):
    antes = copy.deepcopy(panel.store)
    for ruta in ("suspender", "cerrar-sesiones"):
        _pet(client, "POST", f"/usuarios/{panel.id_dueno}/{ruta}", panel.dueno)
    _eliminar(client, panel, panel.id_dueno, correo=DUENO)
    _intacto(panel, antes)
    assert _auditoria(client, panel) == []


# ==================== INV-055 ====================

def _todas_las_respuestas(client, panel) -> list:
    uid = panel.id_victima
    return [
        _pet(client, "GET", "/usuarios", panel.dueno), _pet(client, "GET", f"/usuarios/{uid}", panel.dueno),
        _pet(client, "POST", f"/usuarios/{uid}/cerrar-sesiones", panel.dueno),
        _pet(client, "POST", f"/usuarios/{uid}/suspender", panel.dueno),
        _pet(client, "POST", f"/usuarios/{uid}/reactivar", panel.dueno), _pet(client, "GET", "/auditoria", panel.dueno),
    ]


def test_inv055_ninguna_respuesta_incluye_hashed_password(client, panel):
    panel.store[VICTIMA]["hashed_password"] = HASH_DUENO
    respuestas = _todas_las_respuestas(client, panel)
    assert all(r.status_code == 200 for r in respuestas)
    for r in respuestas:
        assert "hashed_password" not in r.text and HASH_DUENO not in r.text and "$2b$" not in r.text


def test_inv055_respuestas_solo_con_claves_de_lista_blanca(client, panel, bd):
    hostil = _fila_bd(hashed_password="$2b$secreto", session_version=7, telefono="573001112233", ip="1.2.3.4",
                      uso={"transacciones": 3, "monto_total": 99.5, "descripcion": "secreta"})
    completo = _fila_bd(uso={"transacciones": 1, "categorias": 2, "presupuestos": 3, "metas": 4, "recurrentes": 5,
                             "whatsapp_conectado": True, "monto": 5, "nombres_categoria": ["x"]}, token="t", is_active=True)
    bd.respuestas.update({
        "admin_listar_usuarios": {"total": 1, "usuarios": [hostil], "hashed_password": "x", "extra": 1},
        "admin_detalle_usuario": completo,
        "admin_suspender_usuario": "ok", "admin_cerrar_sesiones_usuario": "ok",
        "admin_auditoria": {"total": 1, "registros": [{"id": 4, "fecha": "2026-11-25T10:00:00Z", "accion": "suspender",
                                                       "usuario_id": _uid("a@b.co"), "usuario_correo": None, "ip": "1.1.1.1"}]},
    })
    lista = _pet(client, "GET", "/usuarios", panel.dueno).json()
    assert set(lista) == {"generado_en", "pagina", "por_pagina", "total", "total_paginas", "usuarios"}
    assert set(lista["usuarios"][0]) == {"id", "correo", "nombre", "estado", "moneda", "registrado_en", "ultimo_acceso", "es_dueno", "uso"}
    assert lista["usuarios"][0]["uso"] == {"transacciones": 3}
    for r in (_pet(client, "GET", f"/usuarios/{panel.id_victima}", panel.dueno),
              _pet(client, "POST", f"/usuarios/{panel.id_victima}/suspender", panel.dueno),
              _pet(client, "POST", f"/usuarios/{panel.id_victima}/cerrar-sesiones", panel.dueno)):
        d = r.json()
        assert set(d) == {"id", "correo", "nombre", "estado", "moneda", "registrado_en", "ultimo_acceso", "es_dueno", "uso"}
        assert set(d["uso"]) == {"transacciones", "categorias", "presupuestos", "metas", "recurrentes", "whatsapp_conectado"}
    reg = _pet(client, "GET", "/auditoria", panel.dueno).json()
    assert set(reg) == {"generado_en", "pagina", "por_pagina", "total", "total_paginas", "registros"}
    assert set(reg["registros"][0]) == {"id", "fecha", "accion", "usuario_id", "usuario_correo"}
    texto = json.dumps([lista, reg])
    for prohibido in ("$2b$", "573001112233", "1.2.3.4", "monto", "descripcion", "session_version", "token", "secreta"):
        assert prohibido not in texto
    # sin lo esencial (estado inválido) → 503
    bd.respuestas["admin_listar_usuarios"] = {"total": 1, "usuarios": [_fila_bd(estado="rara")]}
    assert _pet(client, "GET", "/usuarios", panel.dueno).status_code == 503


def test_inv055_el_uso_son_solo_conteos_enteros_no_negativos(client, panel, bd):
    bd.respuestas["admin_detalle_usuario"] = _fila_bd(uso={
        "transacciones": -1, "categorias": "5", "presupuestos": True, "metas": 2.5, "recurrentes": 7, "whatsapp_conectado": "si"})
    uso = _pet(client, "GET", f"/usuarios/{panel.id_victima}", panel.dueno).json()["uso"]
    assert uso == {"transacciones": 0, "categorias": 0, "presupuestos": 0, "metas": 0, "recurrentes": 7, "whatsapp_conectado": False}
    assert all(type(v) is int and v >= 0 for k, v in uso.items() if k != "whatsapp_conectado")


def test_inv055_no_se_exponen_montos_descripciones_ni_categorias(client, panel):
    uid = panel.id_victima
    asyncio.run(demo_db.DemoCategoriaDB.crear(uid, "CATEGORIA-CENTINELA", "x", "gasto"))
    demo_db.DemoTransaccionDB._transacciones["t1"] = {"id": "t1", "usuario_id": uid, "monto": 987654.32,
                                                       "descripcion": "DESCRIPCION-CENTINELA"}
    demo_db.DemoMetaDB._metas["m1"] = {"id": "m1", "usuario_id": uid, "nombre": "META-CENTINELA", "monto_objetivo": 4455667}
    whatsapp_db._Memoria.enlaces[uid] = "573009998877"
    respuestas = _todas_las_respuestas(client, panel)
    detalle = respuestas[1].json()
    assert detalle["uso"]["transacciones"] == 1 and detalle["uso"]["categorias"] == 1 and detalle["uso"]["metas"] == 1
    assert detalle["uso"]["whatsapp_conectado"] is True
    for r in respuestas:
        for centinela in ("CENTINELA", "987654", "4455667", "573009998877"):
            assert centinela not in r.text


def test_inv055_session_version_no_sale_en_ninguna_respuesta(client, panel):
    panel.store[VICTIMA]["session_version"] = 4242
    for r in _todas_las_respuestas(client, panel):
        assert "session_version" not in r.text and "4242" not in r.text and '"sv"' not in r.text


def test_inv055_logs_sin_correos_ni_excepciones_completas(client, panel, bd, capsys, caplog):
    bd.respuestas["admin_listar_usuarios"] = RuntimeError(f"fallo con {VICTIMA} y {panel.id_victima} y {PASS_DUENO}")
    bd.respuestas["admin_detalle_usuario"] = _fila_bd(correo=VICTIMA, id=panel.id_victima)
    bd.respuestas["admin_eliminar_usuario"] = RuntimeError(f"borrado de {VICTIMA}")
    r1 = _pet(client, "GET", "/usuarios", panel.dueno)
    r2 = _eliminar(client, panel, panel.id_victima)
    assert r1.status_code == 503 and r2.status_code == 503
    salida = capsys.readouterr()
    todo = salida.out + salida.err + caplog.text + r1.text + r2.text
    for dato in (VICTIMA, panel.id_victima, PASS_DUENO, "fallo con", "borrado de"):
        assert dato not in todo
    assert "RuntimeError" in salida.out + salida.err   # sí el tipo


def test_inv055_la_migracion_no_nombra_columnas_sensibles():
    sql = SQL.read_text(encoding="utf-8").lower()
    for sensible in ("hashed_password", "monto", "descripcion"):
        assert sensible not in sql


# ==================== INV-058 ====================

def test_inv058_eliminar_sin_confirmar_correo_responde_422_y_no_borra(client, panel):
    antes = copy.deepcopy(panel.store)
    r = _pet(client, "DELETE", f"/usuarios/{panel.id_victima}", panel.dueno, json={"contrasena_dueno": PASS_DUENO})
    assert r.status_code == 422 and PASS_DUENO not in r.text
    _intacto(panel, antes)


def test_inv058_correo_distinto_responde_422(client, panel):
    antes = copy.deepcopy(panel.store)
    r = _eliminar(client, panel, panel.id_victima, correo="otra-persona@ejemplo.com")
    assert r.status_code == 422 and r.json() == {"detail": "El correo escrito no coincide con el de la cuenta"}
    assert auth_estado._Memoria.intentos == {}   # la contraseña ni se comprobó
    _intacto(panel, antes)


def test_inv058_correo_con_mayusculas_y_espacios_confirma(client, panel):
    r = _eliminar(client, panel, panel.id_victima, correo="  VICTIMA@Ejemplo.COM ")
    assert r.status_code == 204 and VICTIMA not in panel.store


def test_inv058_eliminar_borra_la_cuenta_con_cascada_y_llama_a_borrar_de_cuenta(client, panel, monkeypatch):
    uid = panel.id_victima
    asyncio.run(demo_db.DemoCategoriaDB.crear(uid, "Comida", "x", "gasto"))
    demo_db.DemoTransaccionDB._transacciones["t1"] = {"id": "t1", "usuario_id": uid, "monto": 5}
    demo_db.DemoTransaccionDB._transacciones["t2"] = {"id": "t2", "usuario_id": panel.id_otro, "monto": 6}
    whatsapp_db._Memoria.enlaces[uid] = "573001112233"
    llamadas = []
    original = auth_estado.borrar_de_cuenta

    async def espia(correo):
        llamadas.append(correo)
        return await original(correo)
    monkeypatch.setattr(auth_estado, "borrar_de_cuenta", espia)
    r = _eliminar(client, panel, uid)
    assert r.status_code == 204 and r.content == b"" and r.headers["cache-control"] == "no-store"
    assert VICTIMA not in panel.store and llamadas == [VICTIMA]
    assert list(demo_db.DemoTransaccionDB._transacciones) == ["t2"] and not demo_db.DemoCategoriaDB._categorias
    assert uid not in whatsapp_db._Memoria.enlaces
    registros = _auditoria(client, panel)
    assert [(g["accion"], g["usuario_id"], g["usuario_correo"]) for g in registros] == [("eliminar", uid, None)]


def test_inv058_si_falla_la_limpieza_de_autenticacion_la_baja_no_se_revierte(client, panel, monkeypatch, capsys):
    async def falla(_correo):
        raise EstadoNoDisponible("simulado")
    monkeypatch.setattr(auth_estado, "borrar_de_cuenta", falla)
    r = _eliminar(client, panel, panel.id_victima)
    assert r.status_code == 204 and VICTIMA not in panel.store
    assert len(_auditoria(client, panel)) == 1
    salida = capsys.readouterr().out
    assert "no se pudo limpiar" in salida and VICTIMA not in salida


def test_inv058_si_falla_el_borrado_no_queda_auditoria_ni_limpieza(client, panel, monkeypatch):
    llamadas = []

    async def falla(*_a):
        raise EstadoNoDisponible("simulado")

    async def espia(correo):
        llamadas.append(correo)
    monkeypatch.setattr(admin_db, "eliminar", falla)
    monkeypatch.setattr(auth_estado, "borrar_de_cuenta", espia)
    r = _eliminar(client, panel, panel.id_victima)
    assert r.status_code == 503 and r.headers["cache-control"] == "no-store"
    assert r.json() == {"detail": admin_routes.MSG_503}
    assert VICTIMA in panel.store and llamadas == [] and _auditoria(client, panel) == []


def test_inv058_usuario_inexistente_responde_404(client, panel):
    r = _eliminar(client, panel, str(uuid.uuid4()), correo="nadie@ejemplo.com")
    assert r.status_code == 404 and r.json() == {"detail": "Usuario no encontrado"}
    assert auth_estado._Memoria.intentos == {}


def test_inv058_el_enlace_de_whatsapp_se_borra_por_cascada(client, panel):
    whatsapp_db._Memoria.enlaces[panel.id_victima] = "573001112233"
    whatsapp_db._Memoria.enlaces[panel.id_otro] = "573004445566"
    assert _eliminar(client, panel, panel.id_victima).status_code == 204
    assert whatsapp_db._Memoria.enlaces == {panel.id_otro: "573004445566"}


def test_inv058_reutiliza_la_limpieza_de_la_baja_propia(client, panel):
    clave = auth_estado.huella_correo(VICTIMA)
    otra = auth_estado.huella_correo(OTRO)
    asyncio.run(auth_estado.login_reservar(VICTIMA))
    asyncio.run(auth_estado.login_reservar(OTRO))
    asyncio.run(auth_estado.codigo_emitir(VICTIMA, "reset", "123456"))
    assert clave in auth_estado._Memoria.intentos and (clave, "reset") in auth_estado._Memoria.codigos
    assert _eliminar(client, panel, panel.id_victima).status_code == 204
    assert clave not in auth_estado._Memoria.intentos and (clave, "reset") not in auth_estado._Memoria.codigos
    assert otra in auth_estado._Memoria.intentos
    from app.api.routes import users as users_routes
    import inspect
    assert "auth_estado.borrar_de_cuenta" in inspect.getsource(users_routes.delete_current_user)


def test_inv058_eliminar_sin_contrasena_dueno_responde_422_y_no_borra(client, panel):
    antes = copy.deepcopy(panel.store)
    r = _pet(client, "DELETE", f"/usuarios/{panel.id_victima}", panel.dueno, json={"confirmar_correo": VICTIMA})
    assert r.status_code == 422
    _intacto(panel, antes)


def test_inv058_contrasena_dueno_incorrecta_responde_403_generico_y_no_borra(client, panel):
    antes = copy.deepcopy(panel.store)
    r = _eliminar(client, panel, panel.id_victima, contrasena="incorrecta-123")
    assert r.status_code == 403 and r.json() == {"detail": "Contraseña incorrecta"}
    assert r.headers["cache-control"] == "no-store" and "incorrecta-123" not in r.text
    _intacto(panel, antes)


def test_inv058_contrasena_incorrecta_cuenta_como_fallo_y_cinco_bloquean_como_el_login(client, panel):
    for _ in range(5):
        assert _eliminar(client, panel, panel.id_victima, contrasena="mala-contrasena").status_code == 403
    r = _eliminar(client, panel, panel.id_victima)   # ya con la contraseña CORRECTA
    assert r.status_code == 429 and r.json() == {"detail": "Demasiados intentos fallidos. Intenta de nuevo en 15 minutos."}
    assert VICTIMA in panel.store and _auditoria(client, panel) == []
    # mismo bloqueo que el login del Dueño
    panel.store[DUENO]["hashed_password"] = HASH_DUENO
    login = client.post("/api/v1/auth/login", json={"email": DUENO, "password": PASS_DUENO})
    assert login.status_code == 429


def test_inv058_contrasena_correcta_reinicia_la_serie_de_fallos(client, panel):
    for _ in range(3):
        assert _eliminar(client, panel, panel.id_victima, contrasena="mala-contrasena").status_code == 403
    clave = auth_estado.huella_correo(DUENO)
    assert auth_estado._Memoria.intentos[clave]["fallos"] == 3
    assert _eliminar(client, panel, panel.id_victima).status_code == 204
    assert clave not in auth_estado._Memoria.intentos


def test_inv058_la_contrasena_se_verifica_con_ejecutar_bcrypt_y_la_huella_del_correo_del_dueno(client, panel, monkeypatch):
    bcrypt_llamadas, reservas, resoluciones = [], [], []
    o_bcrypt, o_reservar, o_resolver = auth_estado.ejecutar_bcrypt, auth_estado.login_reservar, auth_estado.login_resolver

    async def bcrypt_espia(operacion, fn, *args):
        bcrypt_llamadas.append(operacion)
        return await o_bcrypt(operacion, fn, *args)

    async def reservar(correo):
        reservas.append(correo)
        return await o_reservar(correo)

    async def resolver(correo, acierto):
        resoluciones.append((correo, acierto))
        return await o_resolver(correo, acierto)
    monkeypatch.setattr(auth_estado, "ejecutar_bcrypt", bcrypt_espia)
    monkeypatch.setattr(auth_estado, "login_reservar", reservar)
    monkeypatch.setattr(auth_estado, "login_resolver", resolver)
    assert _eliminar(client, panel, panel.id_victima, contrasena="mala-contrasena").status_code == 403
    assert bcrypt_llamadas == ["verificar_contrasena"] and reservas == [DUENO] and resoluciones == [(DUENO, False)]
    assert auth_estado.huella_correo(DUENO) in auth_estado._Memoria.intentos   # la clave del login: los fallos se suman
    assert auth_estado.huella_correo(VICTIMA) not in auth_estado._Memoria.intentos


def test_inv058_la_contrasena_no_llega_a_logs_ni_auditoria(client, panel, monkeypatch, capsys, caplog):
    textos = [_eliminar(client, panel, panel.id_victima, contrasena="mala-ContraseñaSECRETA").text]
    textos.append(_eliminar(client, panel, panel.id_victima, contrasena="x" * 129).text)   # 422

    async def falla(*_a):
        raise RuntimeError(f"error con {PASS_DUENO}")
    monkeypatch.setattr(admin_db, "eliminar", falla)
    textos.append(_eliminar(client, panel, panel.id_victima).text)   # 503
    monkeypatch.undo()
    textos.append(_eliminar(client, panel, panel.id_victima).text)   # 204
    salida = capsys.readouterr()
    todo = salida.out + salida.err + caplog.text + "".join(textos) + json.dumps(admin_db._Memoria.auditoria, default=str)
    for contrasena in (PASS_DUENO, "mala-ContraseñaSECRETA"):
        assert contrasena not in todo


def test_inv058_suspender_reactivar_y_cerrar_sesiones_no_piden_contrasena(client, panel):
    uid = panel.id_victima
    for ruta in ("suspender", "reactivar", "cerrar-sesiones"):
        r = _pet(client, "POST", f"/usuarios/{uid}/{ruta}", panel.dueno)   # sin cuerpo
        assert r.status_code == 200, ruta
    assert auth_estado._Memoria.intentos == {}


def test_inv058_el_cuerpo_se_lee_con_tope_real_de_2kb_aunque_content_length_mienta(client, panel):
    antes = copy.deepcopy(panel.store)
    grande = json.dumps({"confirmar_correo": VICTIMA, "contrasena_dueno": PASS_DUENO, "x": "y" * 3000}).encode()
    url = f"/usuarios/{panel.id_victima}"
    r = _pet(client, "DELETE", url, {**panel.dueno, "content-length": "20"}, content=grande)   # miente: dice 20 bytes
    assert r.status_code == 413 and r.json() == {"detail": "El cuerpo es demasiado grande"}
    assert r.headers["cache-control"] == "no-store"

    def trozos():   # sin Content-Length: flujo en trozos
        for _ in range(5):
            yield b" " * 600
    assert _pet(client, "DELETE", url, panel.dueno, content=trozos()).status_code == 413
    assert _pet(client, "POST", f"{url}/suspender", panel.dueno, content=b"z" * 4096).status_code == 413
    # un cuerpo en POST de hasta 2 KB se ignora
    assert _pet(client, "POST", f"{url}/cerrar-sesiones", panel.dueno, content=b"z" * 2048).status_code == 200
    assert VICTIMA in panel.store and not panel.store[VICTIMA]["suspendida"]
    assert auth_estado._Memoria.intentos == {}
    del antes

    # un no-Dueño recibe el 404 sin que se lea el cuerpo
    lecturas = []

    async def receive():
        lecturas.append(1)
        return {"type": "http.request", "body": b"x" * 5000, "more_body": False}
    enviados = []

    async def send(msg):
        enviados.append(msg)
    token = panel.otro["Authorization"].encode()
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "DELETE", "scheme": "http",
             "path": BASE + url, "raw_path": (BASE + url).encode(), "query_string": b"", "root_path": "",
             "headers": [(b"authorization", token), (b"content-length", b"5000")], "client": ("127.0.0.1", 1), "server": ("t", 80)}
    asyncio.run(app(scope, receive, send))
    assert enviados[0]["status"] == 404 and lecturas == []


@pytest.mark.parametrize("kw", [
    {}, {"content": b"no es json"}, {"json": []}, {"json": "texto"}, {"json": {"confirmar_correo": VICTIMA}},
    {"json": {"confirmar_correo": VICTIMA, "contrasena_dueno": PASS_DUENO, "extra": 1}},
    {"json": {"confirmar_correo": 12345, "contrasena_dueno": PASS_DUENO}},
    {"json": {"confirmar_correo": VICTIMA, "contrasena_dueno": 123456}},
    {"json": {"confirmar_correo": "ab", "contrasena_dueno": PASS_DUENO}},
    {"json": {"confirmar_correo": "a" * 256, "contrasena_dueno": PASS_DUENO}},
    {"json": {"confirmar_correo": VICTIMA, "contrasena_dueno": ""}},
    {"json": {"confirmar_correo": VICTIMA, "contrasena_dueno": "x" * 129}},
    {"json": {"confirmar_correo": VICTIMA, "contrasena_dueno": None}},
])
def test_inv058_cuerpo_invalido_responde_422(client, panel, kw):
    antes = copy.deepcopy(panel.store)
    r = _pet(client, "DELETE", f"/usuarios/{panel.id_victima}", panel.dueno, **kw)
    assert r.status_code == 422 and r.headers["cache-control"] == "no-store"
    assert PASS_DUENO not in r.text and "x" * 129 not in r.text
    _intacto(panel, antes)


def test_inv058_si_el_borrado_excede_5s_responde_503_sin_dejar_la_auditoria_a_medias(client, panel, bd, monkeypatch):
    """El plazo de la llamada es de 4 s (cliente) dentro del presupuesto de 5 s; aquí se acorta para no esperar."""
    monkeypatch.setattr(auth_estado, "PLAZO_LLAMADA_SEG", 0.3)
    llamadas = []

    async def espia(correo):
        llamadas.append(correo)
    monkeypatch.setattr(auth_estado, "borrar_de_cuenta", espia)
    bd.respuestas["admin_detalle_usuario"] = _fila_bd(id=panel.id_victima, correo=VICTIMA)
    bd.respuestas["admin_eliminar_usuario"] = lambda _a: time.sleep(1.2)
    inicio = time.monotonic()
    r = _eliminar(client, panel, panel.id_victima)
    assert time.monotonic() - inicio < 5
    assert r.status_code == 503 and r.headers["cache-control"] == "no-store"
    assert llamadas == []   # la limpieza se omite: la función SQL es atómica (auditoría y borrado juntos o ninguno)
    assert [n for n, _ in bd.llamadas].count("admin_eliminar_usuario") == 1   # una sola función: no hay pasos sueltos


# ==================== INV-059 ====================

def test_inv059_cada_accion_exitosa_deja_un_registro(client, panel):
    uid = panel.id_victima
    for i in range(3):
        _alta(panel.store, f"u{i}@ejemplo.com", creado=f"2026-11-1{i}T10:00:00")
    lista = _pet(client, "GET", "/usuarios", panel.dueno)
    assert lista.status_code == 200 and lista.headers["cache-control"] == "no-store"
    assert lista.json()["por_pagina"] == 25 and lista.json()["total"] == 6
    assert _pet(client, "POST", f"/usuarios/{uid}/suspender", panel.dueno).json()["estado"] == "suspendida"
    assert _pet(client, "POST", f"/usuarios/{uid}/reactivar", panel.dueno).json()["estado"] == "activa"
    assert _pet(client, "POST", f"/usuarios/{uid}/cerrar-sesiones", panel.dueno).status_code == 200
    assert _eliminar(client, panel, uid).status_code == 204
    registros = _auditoria(client, panel)
    assert [g["accion"] for g in registros] == ["eliminar", "cerrar_sesiones", "reactivar", "suspender"]   # más reciente primero
    assert {g["usuario_id"] for g in registros} == {uid}


def test_inv059_acciones_rechazadas_o_fallidas_no_dejan_registro(client, panel, monkeypatch):
    uid = panel.id_victima
    desconocido = str(uuid.uuid4())
    assert _pet(client, "POST", f"/usuarios/{desconocido}/suspender", panel.dueno).status_code == 404
    assert _pet(client, "POST", f"/usuarios/{uid}/reactivar", panel.dueno).status_code == 409   # no está suspendida
    assert _pet(client, "POST", f"/usuarios/{panel.id_dueno}/suspender", panel.dueno).status_code == 409
    assert _eliminar(client, panel, uid, correo="otro@ejemplo.com").status_code == 422
    assert _eliminar(client, panel, uid, contrasena="mala").status_code == 403
    _alta(panel.store, "pendiente@ejemplo.com", activo=False)
    assert _pet(client, "POST", f"/usuarios/{_uid('pendiente@ejemplo.com')}/suspender", panel.dueno).status_code == 409

    async def falla(*_a):
        raise EstadoNoDisponible("simulado")
    monkeypatch.setattr(admin_db, "suspender", falla)
    assert _pet(client, "POST", f"/usuarios/{uid}/suspender", panel.dueno).status_code == 503
    assert admin_db._Memoria.auditoria == []


def test_inv059_el_registro_solo_tiene_usuario_id_accion_y_fecha(client, panel):
    _pet(client, "POST", f"/usuarios/{panel.id_victima}/suspender", panel.dueno)
    (fila,) = admin_db._Memoria.auditoria
    assert set(fila) == {"id", "creado_en", "accion", "usuario_id"}
    (reg,) = _auditoria(client, panel)
    assert set(reg) == {"id", "fecha", "accion", "usuario_id", "usuario_correo"}
    sql = SQL.read_text(encoding="utf-8")
    definicion = sql[sql.index("create table if not exists public.auditoria_admin"):sql.index("create index if not exists idx_auditoria_admin")]
    assert "references" not in definicion.lower()
    for columna in ("id bigint", "creado_en", "accion text", "usuario_id uuid"):
        assert columna in definicion
    for personal in ("correo", "email", "nombre", "ip ", "detalle", "motivo"):
        assert personal not in definicion.lower()


def test_inv059_el_registro_sobrevive_a_la_baja_del_usuario(client, panel):
    _pet(client, "POST", f"/usuarios/{panel.id_victima}/suspender", panel.dueno)
    assert _eliminar(client, panel, panel.id_victima).status_code == 204
    registros = _auditoria(client, panel)
    assert [(g["accion"], g["usuario_id"], g["usuario_correo"]) for g in registros] == [
        ("eliminar", panel.id_victima, None), ("suspender", panel.id_victima, None)]


def test_inv059_la_auditoria_solo_se_lee_con_get_y_no_hay_rutas_para_editarla(client, panel):
    _pet(client, "POST", f"/usuarios/{panel.id_victima}/suspender", panel.dueno)
    for metodo in ("POST", "PUT", "PATCH", "DELETE"):
        assert _pet(client, metodo, "/auditoria", panel.dueno).status_code == 405
        for ruta in ("/auditoria/1", "/auditoria/1/editar"):
            assert _pet(client, metodo, ruta, panel.dueno).status_code == 404
    assert len(admin_db._Memoria.auditoria) == 1
    rutas = {r.path for r in app.routes}
    assert not any("auditoria" in r for r in rutas)   # todo pasa por el despachador: ninguna ruta propia de edición


def test_inv059_auditoria_paginada_de_25_en_orden_descendente(client, panel):
    for _ in range(30):
        admin_db._mem_auditar("cerrar_sesiones", panel.id_victima)
    p1 = _pet(client, "GET", "/auditoria", panel.dueno).json()
    p2 = _pet(client, "GET", "/auditoria?pagina=2", panel.dueno).json()
    assert p1["total"] == 30 and p1["por_pagina"] == 25 and p1["total_paginas"] == 2
    assert [g["id"] for g in p1["registros"]] == list(range(30, 5, -1))
    assert [g["id"] for g in p2["registros"]] == list(range(5, 0, -1))
    assert _pet(client, "GET", "/auditoria?pagina=0", panel.dueno).status_code == 422
    vacia = _pet(client, "GET", "/auditoria", panel.dueno)
    assert vacia.status_code == 200


def test_inv059_la_auditoria_muestra_el_correo_solo_si_la_cuenta_existe(client, panel):
    _pet(client, "POST", f"/usuarios/{panel.id_victima}/cerrar-sesiones", panel.dueno)
    _pet(client, "POST", f"/usuarios/{panel.id_otro}/cerrar-sesiones", panel.dueno)
    antes = {g["usuario_id"]: g["usuario_correo"] for g in _auditoria(client, panel)}
    assert antes == {panel.id_victima: VICTIMA, panel.id_otro: OTRO}
    del panel.store[OTRO]
    despues = {g["usuario_id"]: g["usuario_correo"] for g in _auditoria(client, panel)}
    assert despues == {panel.id_victima: VICTIMA, panel.id_otro: None}


# ==================== INV-060 ====================

def test_inv060_limite_60_por_minuto_responde_429_con_no_store(client, panel):
    for _ in range(60):
        assert _pet(client, "GET", "/usuarios", panel.dueno).status_code == 200
    r = _pet(client, "GET", "/usuarios", panel.dueno)
    assert r.status_code == 429 and r.headers["cache-control"] == "no-store"
    assert r.json() == {"detail": "Demasiadas consultas. Intenta de nuevo en un minuto."}


def test_inv060_limite_20_escrituras_por_minuto_responde_429(client, panel):
    for _ in range(20):
        assert _pet(client, "POST", f"/usuarios/{panel.id_victima}/cerrar-sesiones", panel.dueno).status_code == 200
    r = _pet(client, "POST", f"/usuarios/{panel.id_victima}/cerrar-sesiones", panel.dueno)
    assert r.status_code == 429 and r.headers["cache-control"] == "no-store"
    assert panel.store[VICTIMA]["session_version"] == 20
    assert _pet(client, "GET", "/usuarios", panel.dueno).status_code == 200   # las lecturas siguen (el tope de 60 no se alcanzó)


def test_inv060_el_405_cuenta_para_el_limite(client, panel):
    for _ in range(60):
        assert _pet(client, "PUT", "/usuarios", panel.dueno).status_code == 405
    assert _pet(client, "PUT", "/usuarios", panel.dueno).status_code == 429


def test_inv060_no_dueno_sobre_el_limite_recibe_404_nunca_429(client, panel):
    esperado = _sin_date(client.get("/api/v1/no-existe"))
    for i in range(100):
        metodo, ruta = RUTAS[i % len(RUTAS)]
        r = _pet(client, metodo, ruta.format(id=panel.id_victima), panel.otro)
        assert _sin_date(r) == esperado
    assert _pet(client, "GET", "/usuarios", panel.dueno).status_code == 200   # y no gastó el cupo del Dueño


def test_inv060_pagina_de_25_y_tope_de_400_paginas(client, panel):
    for i in range(57):   # 3 + 57 = 60 usuarios
        _alta(panel.store, f"u{i:02d}@ejemplo.com", creado=f"2026-10-{(i % 28) + 1:02d}T10:00:00")
    p1 = _pet(client, "GET", "/usuarios", panel.dueno).json()
    p3 = _pet(client, "GET", "/usuarios?pagina=3", panel.dueno).json()
    assert len(p1["usuarios"]) == 25 and len(p3["usuarios"]) == 10
    assert p1["total"] == 60 and p1["total_paginas"] == 3 and p1["por_pagina"] == 25 and p1["pagina"] == 1
    assert p1["usuarios"][0]["correo"] == VICTIMA   # created_at descendente
    ids = [u["correo"] for u in p1["usuarios"]] + [u["correo"] for u in _pet(client, "GET", "/usuarios?pagina=2", panel.dueno).json()["usuarios"]] \
        + [u["correo"] for u in p3["usuarios"]]
    assert len(set(ids)) == 60
    assert _pet(client, "GET", "/usuarios?pagina=0", panel.dueno).status_code == 422
    assert _pet(client, "GET", "/usuarios?pagina=401", panel.dueno).status_code == 422
    vacia = _pet(client, "GET", "/usuarios?pagina=400", panel.dueno)
    assert vacia.status_code == 200 and vacia.json()["usuarios"] == [] and vacia.json()["total_paginas"] == 3
    assert _pet(client, "GET", "/usuarios?por_pagina=1000", panel.dueno).json()["por_pagina"] == 25
    vacio = {"total": 0, "usuarios": []}
    assert admin_routes._pagina_de(vacio, 1, "usuarios", lambda f: f)["total_paginas"] == 1


@pytest.mark.parametrize("valor", ["abc", "-1", "1.5", "", "01", "%201", "+1", "1&pagina=2", "4000", "٣"])
def test_inv060_pagina_invalida_responde_422(client, panel, valor):
    for ruta in ("/usuarios", "/auditoria"):
        r = client.get(f"{BASE}{ruta}?pagina={valor}", headers=panel.dueno)
        assert r.status_code == 422 and r.headers["cache-control"] == "no-store", (ruta, valor)


def test_inv060_busqueda_por_correo_o_nombre_sin_distinguir_mayusculas(client, panel):
    _alta(panel.store, "ana@ejemplo.com", nombre="Zeta Uno")
    _alta(panel.store, "beto@ejemplo.com", nombre="Ana Pérez")
    _alta(panel.store, "carla@ejemplo.com", nombre="Carla")
    for q in ("ANA", "ana", "aNa"):
        r = _pet(client, "GET", f"/usuarios?q={q}", panel.dueno).json()
        assert {u["correo"] for u in r["usuarios"]} == {"ana@ejemplo.com", "beto@ejemplo.com"} and r["total"] == 2
    assert _pet(client, "GET", "/usuarios?q=%20%20", panel.dueno).json()["total"] == 6   # vacía = sin filtro


@pytest.mark.parametrize("q", ["%", "_", "\\", "' or 1=1 --", '"; drop table users; --', "a,id.eq.1)"])
def test_inv060_busqueda_escapa_comodines(client, panel, q):
    _alta(panel.store, "con%raro@ejemplo.com", nombre="Cien%")
    r = client.get(f"{BASE}/usuarios", params={"q": q}, headers=panel.dueno)
    assert r.status_code == 200
    esperado = {"%": 1, "_": 0}.get(q, 0)
    assert r.json()["total"] == esperado, q   # nunca «todos»: el texto es literal
    assert len(panel.store) == 4


def test_inv060_busqueda_rechaza_caracteres_de_control_y_mas_de_60_caracteres(client, panel):
    for q in ("a\x00b", "a\nb", "a\tb", "x" * 61, "a\x7fb"):
        r = client.get(f"{BASE}/usuarios", params={"q": q}, headers=panel.dueno)
        assert r.status_code == 422 and r.headers["cache-control"] == "no-store", repr(q)
    assert client.get(f"{BASE}/usuarios", params={"q": "x" * 60}, headers=panel.dueno).status_code == 200
    assert client.get(f"{BASE}/usuarios?q=a&q=b", headers=panel.dueno).status_code == 422


@pytest.mark.parametrize("q", ["' or 1=1 --", '"; drop table users; --', "a,id.eq.1)", "%_\\"])
def test_inv060_busqueda_con_comillas_y_sql_se_trata_como_texto(client, panel, bd, q):
    bd.respuestas["admin_listar_usuarios"] = {"total": 0, "usuarios": []}
    r = client.get(f"{BASE}/usuarios", params={"q": q}, headers=panel.dueno)
    assert r.status_code == 200 and r.json()["usuarios"] == []
    (nombre, args), = bd.llamadas
    assert nombre == "admin_listar_usuarios" and args == {"p_q": q, "p_limite": 25, "p_desplazamiento": 0}   # parámetro, sin tocar
    sql = SQL.read_text(encoding="utf-8")
    assert "execute format" not in sql.split("create or replace function public.admin_listar_usuarios")[1].split("$$;")[0]


def test_inv060_la_lista_hace_una_sola_llamada_a_la_bd(client, panel, bd):
    bd.respuestas["admin_listar_usuarios"] = {"total": 1, "usuarios": [_fila_bd()]}
    assert _pet(client, "GET", "/usuarios?pagina=3&q=ana", panel.dueno).status_code == 200
    assert bd.llamadas == [("admin_listar_usuarios", {"p_q": "ana", "p_limite": 25, "p_desplazamiento": 50})]
    bd.llamadas.clear()
    bd.respuestas["admin_auditoria"] = {"total": 0, "registros": []}
    assert _pet(client, "GET", "/auditoria", panel.dueno).status_code == 200
    assert bd.llamadas == [("admin_auditoria", {"p_limite": 25, "p_desplazamiento": 0})]


def test_inv060_bd_lenta_responde_503_en_5s(client, panel, bd, monkeypatch):
    monkeypatch.setattr(auth_estado, "PLAZO_LLAMADA_SEG", 0.3)   # el real es 4 s dentro del presupuesto de 5 s
    bd.respuestas["admin_listar_usuarios"] = lambda _a: time.sleep(1.0)
    inicio = time.monotonic()
    r = _pet(client, "GET", "/usuarios", panel.dueno)
    assert time.monotonic() - inicio < 5 and auth_estado.PRESUPUESTO_PETICION_SEG <= 5
    assert r.status_code == 503 and r.headers["cache-control"] == "no-store"
    assert r.json() == {"detail": admin_routes.MSG_503}
    assert auth_estado.PLAZO_LLAMADA_SEG <= 5


def test_inv060_ejecutor_lleno_responde_503_sin_encolar(client, panel, bd, monkeypatch):
    lleno = threading.BoundedSemaphore(1)
    lleno.acquire()   # no queda ninguna ranura libre
    monkeypatch.setattr(auth_estado, "_ranuras", lleno)
    bd.respuestas["admin_listar_usuarios"] = {"total": 0, "usuarios": []}
    inicio = time.monotonic()
    r = _pet(client, "GET", "/usuarios", panel.dueno)
    assert r.status_code == 503 and r.headers["cache-control"] == "no-store" and time.monotonic() - inicio < 1
    assert bd.llamadas == []   # no se encoló nada
