"""CHG-002: configuración segura que nunca impide arrancar, filtro por dueño en la BD,
cuenta activa (INV-017), moneda sin éxito falso y contraseña de registro ≥ 8 (INV-018)."""
import asyncio

import pytest

from app.core.config import Settings
from app.models import plataapp as modelos
from app.models.plataapp import MetaDB, TransaccionDB
from app.models.user import UserDB
from conftest import auth_header, ip

CLAVE_BUENA = "k" * 40


def _settings(**valores) -> Settings:
    """Crea una configuración sin leer el archivo .env local."""
    return Settings(_env_file=None, **valores)


# ==================== Configuración (INV-019) ====================

@pytest.mark.parametrize("clave", ["", "your-secret-key-change-in-production",
                                   "REPLACE_WITH_RANDOM_SECRET_AT_LEAST_32"])
def test_clave_publica_o_vacia_se_reemplaza_por_una_aleatoria(clave, capsys):
    s = _settings(SECRET_KEY=clave)
    assert s.SECRET_KEY != clave and len(s.SECRET_KEY) >= 32
    assert "[CONFIG]" in capsys.readouterr().out


def test_clave_corta_se_conserva_con_aviso_para_no_cerrar_sesiones(capsys):
    s = _settings(SECRET_KEY="clave-propia-corta")
    assert s.SECRET_KEY == "clave-propia-corta"
    assert "menos de 32" in capsys.readouterr().out


def test_siete_dias_de_sesion_se_aceptan_y_valores_absurdos_vuelven_a_siete_dias():
    assert _settings(SECRET_KEY=CLAVE_BUENA, ACCESS_TOKEN_EXPIRE_MINUTES=10080).ACCESS_TOKEN_EXPIRE_MINUTES == 10080
    assert _settings(SECRET_KEY=CLAVE_BUENA, ACCESS_TOKEN_EXPIRE_MINUTES=30).ACCESS_TOKEN_EXPIRE_MINUTES == 30
    for absurdo in (0, -5, 10 ** 7):
        assert _settings(SECRET_KEY=CLAVE_BUENA, ACCESS_TOKEN_EXPIRE_MINUTES=absurdo).ACCESS_TOKEN_EXPIRE_MINUTES == 10080


def test_algoritmo_no_hmac_se_reemplaza_por_hs256():
    assert _settings(SECRET_KEY=CLAVE_BUENA, ALGORITHM="none").ALGORITHM == "HS256"
    assert _settings(SECRET_KEY=CLAVE_BUENA, ALGORITHM="HS512").ALGORITHM == "HS512"


def test_cors_descarta_comodines_y_valores_que_no_son_origenes():
    s = _settings(SECRET_KEY=CLAVE_BUENA, CORS_ORIGINS=[
        "*", "https://*.vercel.app", "https://finanzyapp.vercel.app/", "ftp://x.com",
        "https://a.com/ruta", "https://user:pw@a.com", "http://localhost:3000",
    ])
    assert s.CORS_ORIGINS == ["https://finanzyapp.vercel.app", "http://localhost:3000"]


def test_produccion_desactiva_debug_y_arranca_aunque_falte_supabase(capsys):
    s = _settings(SECRET_KEY=CLAVE_BUENA, ENVIRONMENT="production", DEBUG=True)
    assert s.DEBUG is False
    assert "SUPABASE" in capsys.readouterr().out


def test_debug_esta_apagado_por_defecto():
    assert _settings(SECRET_KEY=CLAVE_BUENA).DEBUG is False


def test_cors_no_permite_otros_proyectos_de_vercel(client):
    malicioso = client.options("/api/v1/categorias", headers={
        "Origin": "https://atacante.vercel.app", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in malicioso.headers
    propio = client.options("/api/v1/categorias", headers={
        "Origin": "https://finanzyapp.vercel.app", "Access-Control-Request-Method": "GET"})
    assert propio.headers.get("access-control-allow-origin") == "https://finanzyapp.vercel.app"


# ==================== Filtro por dueño en la BD (INV-001, defensa en profundidad) ====================

class _ConsultaGrabada:
    """Imita el cliente de Supabase y anota cada filtro .eq() aplicado."""

    def __init__(self, filtros: list):
        self.filtros = filtros

    def __getattr__(self, _nombre):
        return lambda *a, **k: self

    def eq(self, campo, valor):
        self.filtros.append((campo, valor))
        return self

    def execute(self):
        return type("R", (), {"data": []})()


class _ClienteGrabado:
    def __init__(self):
        self.filtros: list = []

    def table(self, _nombre):
        return _ConsultaGrabada(self.filtros)


@pytest.mark.parametrize("operacion", [
    lambda: TransaccionDB.obtener_por_id("t1", "dueno"),
    lambda: TransaccionDB.actualizar("t1", "dueno", monto=5),
    lambda: TransaccionDB.eliminar("t1", "dueno"),
    lambda: modelos.CategoriaDB.obtener_por_id("c1", "dueno"),
    lambda: modelos.CategoriaDB.actualizar("c1", "dueno", "n", "i", "gasto"),
    lambda: modelos.CategoriaDB.eliminar("c1", "dueno"),
    lambda: modelos.PresupuestoDB.obtener_por_id("p1", "dueno"),
    lambda: modelos.PresupuestoDB.actualizar("p1", "dueno", 10),
    lambda: modelos.PresupuestoDB.eliminar("p1", "dueno"),
    lambda: MetaDB.obtener_por_id("m1", "dueno"),
    lambda: MetaDB.actualizar_progreso("m1", "dueno", {"monto_actual": 1}),
    lambda: MetaDB.eliminar("m1", "dueno"),
])
def test_toda_consulta_por_id_en_supabase_filtra_tambien_por_usuario(operacion, monkeypatch):
    cliente = _ClienteGrabado()
    monkeypatch.setattr(modelos, "_supabase_ok", lambda: True)
    monkeypatch.setattr(modelos.SupabaseDB, "get_client", staticmethod(lambda: cliente))
    asyncio.run(operacion())
    assert ("usuario_id", "dueno") in cliente.filtros


def test_modo_demo_no_borra_ni_edita_registros_de_otro_usuario(client):
    meta = client.post("/api/v1/metas", json={"nombre": "Viaje", "monto_objetivo": 100, "fecha_objetivo": "2027-01-01"},
                       headers=auth_header("user-a")).json()
    assert asyncio.run(MetaDB.eliminar(meta["id"], "user-b")) is False
    assert asyncio.run(MetaDB.actualizar_progreso(meta["id"], "user-b", {"monto_actual": 99})) is None
    assert asyncio.run(MetaDB.obtener_por_id(meta["id"], "user-b")) is None
    assert asyncio.run(MetaDB.obtener_por_id(meta["id"], "user-a"))["monto_actual"] == 0


# ==================== Cuenta activa (INV-017) ====================

def _usuario(users, activo=True):
    users["ana@example.com"] = {"id": "u1", "email": "ana@example.com", "hashed_password": "x", "is_active": activo,
                                "full_name": "Ana", "currency": "USD", "session_version": 0}


def test_inv017_token_de_cuenta_no_activa_se_rechaza(client, users):
    _usuario(users, activo=False)
    assert client.get("/api/v1/users/me", headers=auth_header("u1")).status_code == 401
    assert client.get("/api/v1/categorias", headers=auth_header("u1")).status_code == 401


def test_inv017_cuenta_activa_sigue_entrando(client, users):
    _usuario(users)
    assert client.get("/api/v1/users/me", headers=auth_header("u1")).status_code == 200


def test_inv017_supabase_rechaza_cuenta_inactiva():
    class _Cliente:
        def table(self, _):
            return self

        def __getattr__(self, _):
            return lambda *a, **k: self

        def execute(self):
            return type("R", (), {"data": [{"session_version": 0, "is_active": False}]})()

    original = (UserDB._is_supabase_available, modelos.SupabaseDB.get_client)
    try:
        UserDB._is_supabase_available = staticmethod(lambda: True)
        modelos.SupabaseDB.get_client = staticmethod(lambda: _Cliente())
        assert asyncio.run(UserDB.get_session_version("u1")) is None
    finally:
        UserDB._is_supabase_available = staticmethod(original[0])
        modelos.SupabaseDB.get_client = staticmethod(original[1])


# ==================== Moneda sin éxito falso ====================

def test_moneda_si_no_se_guarda_responde_error_y_no_finge_exito(client, users, monkeypatch):
    _usuario(users)

    async def falla(*_):
        return False

    monkeypatch.setattr(UserDB, "update_currency", staticmethod(falla))
    r = client.put("/api/v1/users/me/currency", json={"currency": "EUR"}, headers=auth_header("u1"))
    assert r.status_code == 503
    assert users["ana@example.com"]["currency"] == "USD"


def test_moneda_guardada_se_devuelve_actualizada(client, users, monkeypatch):
    _usuario(users)

    async def guarda(user_id, currency):
        users["ana@example.com"]["currency"] = currency
        return True

    monkeypatch.setattr(UserDB, "update_currency", staticmethod(guarda))
    r = client.put("/api/v1/users/me/currency", json={"currency": "EUR"}, headers=auth_header("u1"))
    assert r.status_code == 200 and r.json()["currency"] == "EUR"


# ==================== Contraseña de registro (INV-018) ====================

def test_inv018_registro_exige_al_menos_8_caracteres(client, users, sent_emails):
    corta = {"email": "bea@example.com", "full_name": "Bea", "password": "Clave12"}
    assert client.post("/api/v1/auth/register", json=corta, headers=ip(2)).status_code == 422
    buena = {**corta, "password": "Clave123"}
    assert client.post("/api/v1/auth/register", json=buena, headers=ip(2)).status_code == 201


def test_moneda_si_supabase_falla_responde_503(client, users, monkeypatch):
    _usuario(users)

    async def revienta(*_):
        raise RuntimeError("Supabase no disponible")

    monkeypatch.setattr(UserDB, "update_currency", staticmethod(revienta))
    r = client.put("/api/v1/users/me/currency", json={"currency": "EUR"}, headers=auth_header("u1"))
    assert r.status_code == 503
