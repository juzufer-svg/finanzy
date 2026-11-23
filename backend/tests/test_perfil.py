"""CHG-012 · REQ-F-014 CA-2 y CA-3 · INV-027: editar el nombre y cambiar la contraseña desde el perfil."""
import pytest

from app.api.sesion import SESION_INVALIDA
from app.core import security
from app.models.user import UserDB
from conftest import ip

CORREO = "ana@example.com"


@pytest.fixture
def ana(users):
    users[CORREO] = {"id": "u1", "email": CORREO, "hashed_password": security.get_password_hash("Vieja1234"),
                     "is_active": True, "full_name": "Ana", "currency": "USD", "session_version": 0}
    return users[CORREO]


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client, password="Vieja1234") -> dict:
    r = client.post("/api/v1/auth/login", json={"email": CORREO, "password": password}, headers=ip(1))
    assert r.status_code == 200
    return _bearer(r.json()["access_token"])


def _cambiar(client, sesion, actual="Vieja1234", nueva="NuevaClave1"):
    return client.post("/api/v1/users/me/password", json={"actual": actual, "nueva": nueva}, headers={**sesion, **ip(1)})


# ── Nombre ────────────────────────────────────────────────────────────────────

def test_cambiar_el_nombre(client, ana):
    sesion = _login(client)
    r = client.put("/api/v1/users/me", json={"full_name": "  Ana   María  "}, headers=sesion)
    assert r.status_code == 200 and r.json()["full_name"] == "Ana María"
    assert client.get("/api/v1/users/me", headers=sesion).json()["full_name"] == "Ana María"
    assert "hashed_password" not in r.json()


@pytest.mark.parametrize("nombre", ["", "A", "   ", "x" * 101])
def test_nombre_invalido_es_422(client, ana, nombre):
    assert client.put("/api/v1/users/me", json={"full_name": nombre}, headers=_login(client)).status_code == 422
    assert ana["full_name"] == "Ana"


def test_si_la_bd_falla_al_guardar_el_nombre_es_503(client, ana, monkeypatch):
    sesion = _login(client)

    async def falla(*args):
        raise RuntimeError("Supabase caído")

    monkeypatch.setattr(UserDB, "update_full_name", staticmethod(falla))
    r = client.put("/api/v1/users/me", json={"full_name": "Otra"}, headers=sesion)
    assert r.status_code == 503 and ana["full_name"] == "Ana"


def test_nombre_sin_sesion_es_rechazado(client, ana):
    assert client.put("/api/v1/users/me", json={"full_name": "Otra"}, headers=_bearer("x")).status_code == 401


# ── Contraseña (INV-027) ──────────────────────────────────────────────────────

def test_inv027_cambiar_contrasena_cierra_las_otras_sesiones_y_mantiene_la_actual(client, ana):
    esta = _login(client)
    otra = _login(client)  # p. ej. el computador del trabajo
    r = _cambiar(client, esta)
    assert r.status_code == 200
    nueva_sesion = _bearer(r.json()["access_token"])

    # La sesión de este dispositivo sigue con el token nuevo; las anteriores quedan cerradas
    assert client.get("/api/v1/users/me", headers=nueva_sesion).status_code == 200
    for vieja in (esta, otra):
        r = client.get("/api/v1/categorias", headers=vieja)
        assert r.status_code == 401 and r.json()["detail"] == SESION_INVALIDA

    # Solo la contraseña nueva sirve para entrar
    assert client.post("/api/v1/auth/login", json={"email": CORREO, "password": "Vieja1234"}, headers=ip(2)).status_code == 401
    _login(client, "NuevaClave1")


def test_inv027_contrasena_actual_incorrecta_es_400_y_no_cambia_nada(client, ana):
    sesion = _login(client)
    r = _cambiar(client, sesion, actual="Equivocada1")
    # 400 y no 401: el frontend cierra la sesión ante un 401
    assert r.status_code == 400 and r.json()["detail"] == "La contraseña actual no es correcta"
    assert ana["session_version"] == 0
    assert client.get("/api/v1/users/me", headers=sesion).status_code == 200
    _login(client)  # la contraseña vieja sigue sirviendo


def test_inv027_cinco_intentos_fallidos_bloquean_15_minutos(client, ana):
    sesion = _login(client)
    for _ in range(5):
        assert _cambiar(client, sesion, actual="Equivocada1").status_code == 400
    # Bloqueado incluso con la contraseña correcta, y también el login (mismo contador, INV-010)
    assert _cambiar(client, sesion).status_code == 429
    assert client.post("/api/v1/auth/login", json={"email": CORREO, "password": "Vieja1234"}, headers=ip(3)).status_code == 429
    assert ana["session_version"] == 0


@pytest.mark.parametrize("nueva", ["corta12", "x" * 129])
def test_inv018_la_nueva_tiene_de_8_a_128_caracteres(client, ana, nueva):
    assert _cambiar(client, _login(client), nueva=nueva).status_code == 422
    assert ana["session_version"] == 0


def test_la_nueva_debe_ser_distinta_de_la_actual(client, ana):
    r = _cambiar(client, _login(client), nueva="Vieja1234")
    assert r.status_code == 422 and ana["session_version"] == 0


def test_sin_sesion_valida_no_se_puede_cambiar(client, ana):
    assert _cambiar(client, _bearer("x")).status_code == 401
    assert ana["session_version"] == 0


def test_si_la_bd_falla_al_cambiar_es_503_y_no_cierra_sesiones(client, ana, monkeypatch):
    sesion = _login(client)

    async def falla(*args):
        raise RuntimeError("Supabase caído")

    monkeypatch.setattr(UserDB, "update_password", staticmethod(falla))
    assert _cambiar(client, sesion).status_code == 503
    assert client.get("/api/v1/users/me", headers=sesion).status_code == 200
