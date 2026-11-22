"""INV-003, INV-004 e INV-005: validación de montos, tipos y fechas. (BDD-TRANSACCIONES)"""
import pytest

from conftest import auth_header

A = auth_header("user-a")
BASE = {"categoria_id": "", "monto": 10, "descripcion": "x", "fecha": "2026-11-22", "tipo": "gasto"}


def _post(client, **cambios):
    return client.post("/api/v1/transacciones", json={**BASE, **cambios}, headers=A).status_code


@pytest.mark.parametrize("monto", [0, -5, 10**13])
def test_inv003_montos_fuera_de_rango_se_rechazan(client, monto):
    assert _post(client, monto=monto) == 422


def test_inv003_monto_como_texto_numerico_se_acepta(client):
    assert _post(client, monto="12.5") == 200


def test_inv003_limites_objetivos_y_abonos_positivos(client):
    assert client.post("/api/v1/presupuestos", json={"categoria_id": "c", "limite_mensual": 0, "mes_ano": "2026-11"}, headers=A).status_code == 422
    assert client.post("/api/v1/metas", json={"nombre": "M", "monto_objetivo": -1, "fecha_objetivo": "2027-01-01"}, headers=A).status_code == 422
    meta = client.post("/api/v1/metas", json={"nombre": "M", "monto_objetivo": 100, "fecha_objetivo": "2027-01-01"}, headers=A).json()
    assert client.put(f"/api/v1/metas/{meta['id']}", json={"monto_actual": -1}, headers=A).status_code == 422
    assert client.post(f"/api/v1/metas/{meta['id']}/abonar", json={"monto": 0, "fecha": "2026-11-22"}, headers=A).status_code == 422


def test_inv004_tipo_debe_ser_ingreso_o_gasto(client):
    assert _post(client, tipo="otro") == 422
    assert client.post("/api/v1/categorias", json={"nombre": "X", "icono": "", "tipo": "ahorro"}, headers=A).status_code == 422


@pytest.mark.parametrize("fecha", ["hoy", "2026-13-01", "22/11/2026"])
def test_inv005_fechas_invalidas_se_rechazan(client, fecha):
    assert _post(client, fecha=fecha) == 422


def test_inv005_meses_invalidos_se_rechazan(client):
    assert client.get("/api/v1/transacciones?mes=abc", headers=A).status_code == 422
    assert client.get("/api/v1/transacciones/resumen/2026-13", headers=A).status_code == 422
    assert client.get("/api/v1/presupuestos/2026-1", headers=A).status_code == 422


def test_resumen_del_mes(client):
    client.post("/api/v1/transacciones", json={**BASE, "monto": 100, "tipo": "ingreso"}, headers=A)
    client.post("/api/v1/transacciones", json={**BASE, "monto": 30}, headers=A)
    client.post("/api/v1/transacciones", json={**BASE, "monto": 5, "fecha": "2026-10-01"}, headers=A)  # otro mes
    r = client.get("/api/v1/transacciones/resumen/2026-11", headers=A).json()
    assert r == {"ingresos": 100, "gastos": 30, "balance": 70, "total_transacciones": 2}
