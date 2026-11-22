"""INV-012 (superficie expuesta en producción) e INV-013 (sin respaldo en memoria si la BD falla)."""
import asyncio
import importlib

import pytest

from app.core.config import settings
from app.models import plataapp as modelos


def test_inv012_no_existen_endpoints_de_diagnostico(client):
    for ruta in ("/api/v1/diagnostics", "/api/v1/diagnostics/reset-password", "/api/v1/diagnostics/create-test-user",
                 "/api/v1/diagnostics/test-login"):
        assert client.get(ruta).status_code == 404


def test_inv012_docs_ocultos_en_produccion(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    try:
        prod = importlib.reload(main_module).app
        assert prod.docs_url is None and prod.redoc_url is None and prod.openapi_url is None
    finally:
        monkeypatch.setattr(settings, "ENVIRONMENT", "development")
        importlib.reload(main_module)


def test_health(client):
    assert client.get("/health").json() == {"status": "healthy"}


def test_inv013_si_supabase_falla_se_propaga_el_error_y_no_se_guarda_en_memoria(monkeypatch):
    class _ClienteRoto:
        def table(self, *_):
            raise RuntimeError("Supabase no disponible")

    monkeypatch.setattr(modelos, "_supabase_ok", lambda: True)
    monkeypatch.setattr(modelos.SupabaseDB, "get_client", staticmethod(lambda: _ClienteRoto()))
    with pytest.raises(RuntimeError):
        asyncio.run(modelos.TransaccionDB.crear("u", "", 10, "x", "2026-11-22", "gasto"))
    assert modelos.DemoTransaccionDB._transacciones == {}
