"""INV-008 y REQ-F-008/009: metas y abonos. (BDD-METAS)"""
from app.models.plataapp import MetaDB
from conftest import auth_header

A = auth_header("user-a")


def _meta(client, objetivo=1000):
    return client.post("/api/v1/metas", json={"nombre": "Viaje", "monto_objetivo": objetivo, "fecha_objetivo": "2027-06-01"}, headers=A).json()


def _cantidad_transacciones(client):
    return len(client.get("/api/v1/transacciones", headers=A).json())


def test_abono_suma_a_la_meta_y_registra_gasto_en_ahorro(client):
    meta = _meta(client)
    r = client.post(f"/api/v1/metas/{meta['id']}/abonar", json={"monto": 50, "fecha": "2026-11-22"}, headers=A)
    assert r.status_code == 200
    assert r.json()["monto_actual"] == 50 and abs(r.json()["porcentaje_completado"] - 5) < 1e-9
    gastos = client.get("/api/v1/transacciones", headers=A).json()
    assert len(gastos) == 1 and gastos[0]["tipo"] == "gasto" and gastos[0]["monto"] == 50
    categorias = {c["id"]: c["nombre"] for c in client.get("/api/v1/categorias", headers=A).json()}
    assert categorias[gastos[0]["categoria_id"]] == "Ahorro"


def test_inv008_abono_a_meta_inexistente_no_crea_gasto(client):
    r = client.post("/api/v1/metas/no-existe/abonar", json={"monto": 5, "fecha": "2026-11-22"}, headers=A)
    assert r.status_code == 404
    assert _cantidad_transacciones(client) == 0


def test_inv008_si_falla_actualizar_la_meta_se_revierte_el_gasto(client, monkeypatch):
    meta = _meta(client)

    async def falla(*args, **kwargs):
        raise RuntimeError("BD caída")

    monkeypatch.setattr(MetaDB, "actualizar_progreso", staticmethod(falla))
    r = client.post(f"/api/v1/metas/{meta['id']}/abonar", json={"monto": 5, "fecha": "2026-11-22"}, headers=A)
    assert r.status_code == 500
    assert _cantidad_transacciones(client) == 0


def test_meta_completada_cuando_lo_ahorrado_alcanza_el_objetivo(client):
    meta = _meta(client, objetivo=100)
    r = client.post(f"/api/v1/metas/{meta['id']}/abonar", json={"monto": 100, "fecha": "2026-11-22"}, headers=A).json()
    assert r["porcentaje_completado"] == 100
