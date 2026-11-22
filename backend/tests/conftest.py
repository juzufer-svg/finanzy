"""
Configuración común de las pruebas del backend.

- Se ejecutan sin Supabase: los datos financieros usan la BD demo en memoria.
- Los usuarios se simulan con un almacén en memoria (`users`) que reemplaza a UserDB.
- Los correos no se envían: se registran en `sent_emails`.
- Antes de cada prueba se reinician límites, códigos y datos.

Ejecutar desde `backend/`:  python -m pytest -q
"""
import os
import sys
from pathlib import Path

# Entorno de prueba (antes de importar la app)
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_KEY", None)
os.environ["SECRET_KEY"] = "clave-de-pruebas-con-mas-de-32-caracteres-123"
os.environ.setdefault("ENVIRONMENT", "development")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.api.routes import auth as auth_routes  # noqa: E402
from app.api.routes import asistente as asistente_routes  # noqa: E402
from app.core import security  # noqa: E402
from app.models import demo_db  # noqa: E402
from app.models.user import UserDB  # noqa: E402
from app.utils import email as email_utils  # noqa: E402


@pytest.fixture(autouse=True)
def estado_limpio():
    """Reinicia todo el estado en memoria entre pruebas."""
    for limiter in (
        auth_routes._ip_email_requests,
        auth_routes._email_daily,
        auth_routes._global_daily,
        auth_routes._ip_auth_attempts,
        asistente_routes._por_minuto,
        asistente_routes._por_usuario_dia,
        asistente_routes._global_dia,
    ):
        limiter.reset()
    auth_routes._login_fails.clear()
    email_utils._pending_codes.clear()
    demo_db.DemoTransaccionDB._transacciones.clear()
    demo_db.DemoCategoriaDB._categorias.clear()
    demo_db.DemoPresupuestoDB._presupuestos.clear()
    demo_db.DemoMetaDB._metas.clear()
    yield


@pytest.fixture
def users(monkeypatch):
    """Almacén de usuarios en memoria que reemplaza a UserDB (Supabase)."""
    store: dict[str, dict] = {}

    async def get_by_email(email):
        return store.get(email.lower())

    async def get_by_id(user_id):
        return next((u for u in store.values() if u["id"] == user_id), None)

    async def create(email, password, full_name="", is_active=False, currency="USD"):
        store[email.lower()] = {
            "id": f"id-{email.lower()}", "email": email.lower(), "full_name": full_name,
            "hashed_password": security.get_password_hash(password),
            "is_active": is_active, "currency": currency, "session_version": 0,
        }
        return store[email.lower()]

    async def activate(email):
        store[email.lower()]["is_active"] = True
        return True

    async def update_password(email, new_password):
        user = store.get(email.lower())
        if not user:
            return False
        user["hashed_password"] = security.get_password_hash(new_password)
        user["is_active"] = True
        user["session_version"] = user.get("session_version", 0) + 1  # INV-016
        return True

    async def get_session_version(user_id):
        user = await get_by_id(user_id)
        if user is None or not user.get("is_active"):  # INV-017
            return None
        return user.get("session_version", 0)

    for name, fn in [("get_by_email", get_by_email), ("get_by_id", get_by_id), ("create", create),
                     ("activate", activate), ("update_password", update_password),
                     ("get_session_version", get_session_version)]:
        monkeypatch.setattr(UserDB, name, staticmethod(fn))
    return store


@pytest.fixture
def sent_emails(monkeypatch):
    """Registra los correos en lugar de enviarlos: lista de (destinatario, código, propósito)."""
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        auth_routes, "send_verification_email",
        lambda to, code, purpose="verify": sent.append((to, code, purpose)),
    )
    return sent


@pytest.fixture
def client():
    return TestClient(app)


def auth_header(user_id: str) -> dict:
    return {"Authorization": "Bearer " + security.create_access_token({"sub": user_id})}


def ip(n: int) -> dict:
    """Simula la IP real del visitante tal como la envía Vercel."""
    return {"X-Forwarded-For": f"203.0.113.{n}, 10.0.0.1"}
