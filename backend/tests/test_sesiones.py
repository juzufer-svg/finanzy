"""Sesiones y cambio de contraseña: INV-016, REQ-F-003 CA-4. (BDD-RECUPERACION)"""
import pytest

from app.api.sesion import SESION_INVALIDA
from app.core import security
from app.models.user import UserDB
from conftest import ip

CORREO = "ana@example.com"


def _usuario(users):
    users[CORREO] = {"id": "u1", "email": CORREO, "hashed_password": security.get_password_hash("Vieja1234"),
                     "is_active": True, "full_name": "Ana", "currency": "USD", "session_version": 0}


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client, password="Vieja1234") -> dict:
    r = client.post("/api/v1/auth/login", json={"email": CORREO, "password": password}, headers=ip(1))
    assert r.status_code == 200
    return _bearer(r.json()["access_token"])


def _restablecer(client, sent_emails, nueva="NuevaClave1"):
    client.post("/api/v1/auth/forgot-password", json={"email": CORREO}, headers=ip(1))
    code = [s for s in sent_emails if s[2] == "reset"][-1][1]
    r = client.post("/api/v1/auth/reset-password", json={"email": CORREO, "code": code, "new_password": nueva}, headers=ip(1))
    assert r.status_code == 200


def test_inv016_restablecer_contrasena_cierra_las_sesiones_abiertas(client, users, sent_emails):
    _usuario(users)
    sesion_vieja = _login(client)
    assert client.get("/api/v1/users/me", headers=sesion_vieja).status_code == 200
    assert client.get("/api/v1/categorias", headers=sesion_vieja).status_code == 200

    _restablecer(client, sent_emails)

    for ruta in ("/api/v1/users/me", "/api/v1/categorias", "/api/v1/metas"):
        r = client.get(ruta, headers=sesion_vieja)
        assert r.status_code == 401 and r.json()["detail"] == SESION_INVALIDA
    assert client.put("/api/v1/users/me/currency", json={"currency": "EUR"}, headers=sesion_vieja).status_code == 401
    assert client.delete("/api/v1/users/me", headers=sesion_vieja).status_code == 401

    # Con la contraseña nueva se obtiene una sesión que sí funciona
    sesion_nueva = _login(client, "NuevaClave1")
    assert client.get("/api/v1/users/me", headers=sesion_nueva).status_code == 200
    assert client.get("/api/v1/categorias", headers=sesion_nueva).status_code == 200


def test_inv016_tokens_anteriores_al_cambio_sin_sv_siguen_validos_hasta_un_restablecimiento(client, users, sent_emails):
    """Los tokens emitidos antes de desplegar no traen "sv": valen como versión 0 (nadie pierde la sesión al desplegar)."""
    _usuario(users)
    previo = _bearer(security.create_access_token({"sub": "u1"}))
    assert client.get("/api/v1/users/me", headers=previo).status_code == 200
    _restablecer(client, sent_emails)
    assert client.get("/api/v1/users/me", headers=previo).status_code == 401


def test_inv016_versiones_de_sesion_que_no_coinciden_se_rechazan(client, users):
    _usuario(users)
    users[CORREO]["session_version"] = 2
    for sv in (0, 1, 3, "2", True, None):
        token = _bearer(security.create_access_token({"sub": "u1", "sv": sv}))
        assert client.get("/api/v1/categorias", headers=token).status_code == 401, sv
    assert client.get("/api/v1/categorias", headers=_bearer(security.create_access_token({"sub": "u1", "sv": 2}))).status_code == 200


def test_inv016_token_de_un_usuario_que_ya_no_existe_es_401(client, users):
    token = _bearer(security.create_access_token({"sub": "borrado", "sv": 0}))
    assert client.get("/api/v1/users/me", headers=token).status_code == 401
    assert client.get("/api/v1/categorias", headers=token).status_code == 401


def test_inv016_si_la_bd_falla_se_responde_503_y_no_se_cierra_la_sesion(client, users, monkeypatch):
    _usuario(users)

    async def falla(user_id):
        raise RuntimeError("Supabase caído")

    monkeypatch.setattr(UserDB, "get_session_version", staticmethod(falla))
    token = _bearer(security.create_access_token({"sub": "u1", "sv": 0}))
    assert client.get("/api/v1/categorias", headers=token).status_code == 503
    assert client.get("/api/v1/users/me", headers=token).status_code == 503


def test_login_y_verificacion_emiten_la_version_de_sesion_vigente(client, users, sent_emails):
    _usuario(users)
    users[CORREO]["session_version"] = 4
    token = client.post("/api/v1/auth/login", json={"email": CORREO, "password": "Vieja1234"}, headers=ip(1)).json()["access_token"]
    assert security.decode_token(token)["sv"] == 4

    # verify-email también emite la versión vigente
    users[CORREO]["is_active"] = False
    client.post("/api/v1/auth/resend-code", json={"email": CORREO}, headers=ip(1))
    code = [e for e in sent_emails if e[2] == "verify"][-1][1]
    r = client.post("/api/v1/auth/verify-email", json={"email": CORREO, "code": code}, headers=ip(1))
    assert r.status_code == 200 and security.decode_token(r.json()["access_token"])["sv"] == 4


# ── Modelo real (Supabase simulado) ──────────────────────────────────────────

class _ConsultaFalsa:
    """Imita la cadena table().select()/update().eq().limit().execute() de supabase-py."""

    antes_de_update = None

    def __init__(self, filas, registro):
        self.filas, self.registro, self._update = filas, registro, None

    def select(self, *_):
        return self

    def update(self, valores):
        self._update = valores
        return self

    filtros: list

    def eq(self, columna, valor):
        self.filtros = getattr(self, "filtros", []) + [(columna, valor)]
        return self

    def limit(self, _):
        return self

    def execute(self):
        filas = [f for f in self.filas if all(f[c] == v for c, v in self.filtros)]
        if self._update is not None:
            if self.antes_de_update:
                self.antes_de_update()
                filas = [f for f in self.filas if all(f[c] == v for c, v in self.filtros)]
            for f in filas:
                f.update(self._update)
            self.registro.append(self._update)

        class R:
            data = [dict(f) for f in filas]
        return R()


@pytest.fixture
def supabase_falso(monkeypatch):
    from app.core.supabase import SupabaseDB
    filas = [{"id": "u1", "email": CORREO, "hashed_password": "x", "is_active": False, "session_version": 3}]
    updates: list[dict] = []

    class Cliente:
        def table(self, _):
            return _ConsultaFalsa(filas, updates)

    monkeypatch.setattr(UserDB, "_is_supabase_available", staticmethod(lambda: True))
    monkeypatch.setattr(SupabaseDB, "get_client", staticmethod(lambda: Cliente()))
    return filas, updates


@pytest.mark.anyio
async def test_inv016_update_password_sube_la_version_de_sesion(supabase_falso):
    filas, updates = supabase_falso
    assert await UserDB.update_password("ANA@example.com", "NuevaClave1") is True
    assert filas[0]["session_version"] == 4 and filas[0]["is_active"] is True
    assert security.verify_password("NuevaClave1", filas[0]["hashed_password"])
    assert await UserDB.get_session_version("u1") == 4
    assert await UserDB.get_session_version("otro") is None
    assert await UserDB.update_password("nadie@example.com", "NuevaClave1") is False
    assert len(updates) == 1


@pytest.mark.anyio
async def test_inv016_restablecimientos_simultaneos_suben_la_version_dos_veces(supabase_falso, monkeypatch):
    """Si otro restablecimiento se adelanta entre la lectura y la escritura, se reintenta (no se pisa la versión)."""
    filas, updates = supabase_falso
    pendiente = [True]

    def otro_reset_se_adelanta():
        if pendiente.pop() if pendiente else False:
            filas[0]["session_version"] += 1  # 3 → 4 por el otro restablecimiento

    monkeypatch.setattr(_ConsultaFalsa, "antes_de_update", staticmethod(otro_reset_se_adelanta))
    assert await UserDB.update_password(CORREO, "NuevaClave1") is True
    assert filas[0]["session_version"] == 5


@pytest.fixture
def anyio_backend():
    return "asyncio"
