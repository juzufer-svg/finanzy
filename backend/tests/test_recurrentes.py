"""CHG-012 · REQ-F-016 · INV-025, INV-026: transacciones recurrentes (BDD-RECURRENTES)."""
from datetime import date

import pytest

from app.models import plataapp as modelos
from app.utils.recurrencia import siguiente_fecha
from conftest import auth_header

A = auth_header("user-a")
B = auth_header("user-b")


def _crear(client, headers=A, **extra):
    body = {"tipo": "gasto", "monto": 1_500_000, "descripcion": "Arriendo", "frecuencia": "mensual",
            "proxima_fecha": "2026-11-05", "medio_pago": "transferencia", **extra}
    return client.post("/api/v1/recurrentes", json=body, headers=headers)


def _pendientes(client, hasta="2026-11-23", headers=A):
    return client.get(f"/api/v1/recurrentes/pendientes?hasta={hasta}", headers=headers)


def _transacciones(client, headers=A):
    return client.get("/api/v1/transacciones", headers=headers).json()


# ── Cálculo de fechas (INV-026) ───────────────────────────────────────────────

@pytest.mark.parametrize("actual, ancla, esperada", [
    ("2026-11-05", 5, "2026-12-05"),
    ("2026-12-05", 5, "2027-01-05"),     # cambio de año
    ("2026-01-31", 31, "2026-02-28"),    # mes corto: último día
    ("2026-02-28", 31, "2026-03-31"),    # el ancla 31 no se pierde tras febrero
    ("2028-01-31", 31, "2028-02-29"),    # año bisiesto
    ("2026-04-30", 31, "2026-05-31"),
])
def test_inv026_mensual_respeta_el_dia_ancla(actual, ancla, esperada):
    assert siguiente_fecha(date.fromisoformat(actual), "mensual", ancla).isoformat() == esperada


@pytest.mark.parametrize("actual, ancla, esperada", [
    ("2026-11-15", 15, "2026-11-30"),
    ("2026-11-30", 15, "2026-12-15"),
    ("2026-02-15", 15, "2026-02-28"),    # 30 → último día de febrero
    ("2026-02-28", 30, "2026-03-15"),
    ("2026-11-01", 1, "2026-11-16"),
    ("2026-11-16", 1, "2026-12-01"),
    ("2026-11-20", 20, "2026-12-05"),    # ancla > 15: días 5 y 20
    ("2026-12-05", 20, "2026-12-20"),
    ("2026-12-31", 31, "2027-01-16"),    # ancla 31: días 16 y 31
])
def test_inv026_quincenal_dos_veces_al_mes(actual, ancla, esperada):
    assert siguiente_fecha(date.fromisoformat(actual), "quincenal", ancla).isoformat() == esperada


def test_inv026_semanal_suma_siete_dias():
    assert siguiente_fecha(date(2026, 12, 29), "semanal", 29) == date(2027, 1, 5)


def test_inv026_frecuencia_desconocida_falla():
    with pytest.raises(ValueError):
        siguiente_fecha(date(2026, 11, 1), "diaria", 1)


# ── Crear, listar, editar, eliminar ───────────────────────────────────────────

def test_crear_guarda_el_dia_ancla_y_se_lista(client):
    r = _crear(client, proxima_fecha="2026-11-30")
    assert r.status_code == 200
    rec = r.json()
    assert rec["dia_ancla"] == 30 and rec["activa"] is True and rec["frecuencia"] == "mensual"
    assert [x["id"] for x in client.get("/api/v1/recurrentes", headers=A).json()] == [rec["id"]]


@pytest.mark.parametrize("cambio", [
    {"frecuencia": "diaria"}, {"frecuencia": "anual"}, {"monto": 0}, {"monto": -5}, {"monto": 2e12},
    {"tipo": "otro"}, {"medio_pago": "bitcoin"}, {"proxima_fecha": "2026-13-01"},
    {"proxima_fecha": "2026-11-05T10:00"}, {"descripcion": "x" * 256},
])
def test_crear_con_datos_invalidos_es_422(client, cambio):
    assert _crear(client, **cambio).status_code == 422


def test_fecha_inexistente_es_422(client):
    r = _crear(client, proxima_fecha="2026-02-31")
    assert r.status_code == 422 and r.json()["detail"] == "Fecha inválida (YYYY-MM-DD)"


def test_inv002_no_se_puede_usar_la_categoria_de_otro(client):
    cat_b = client.post("/api/v1/categorias", json={"nombre": "Ajena", "tipo": "gasto"}, headers=B).json()
    assert _crear(client, categoria_id=cat_b["id"]).status_code == 404


def test_editar_cambia_el_ancla_solo_si_cambia_la_fecha(client):
    rec = _crear(client, proxima_fecha="2026-01-31").json()
    # Confirmar enero: la próxima queda en el 28 de febrero, pero el ancla sigue siendo 31
    client.post(f"/api/v1/recurrentes/{rec['id']}/omitir", json={"ocurrencia": "2026-01-31"}, headers=A)
    base = {"tipo": "gasto", "descripcion": "Arriendo", "frecuencia": "mensual", "proxima_fecha": "2026-02-28"}
    editada = client.put(f"/api/v1/recurrentes/{rec['id']}", json={**base, "monto": 1_600_000}, headers=A).json()
    assert editada["monto"] == 1_600_000 and editada["dia_ancla"] == 31
    otra = client.put(f"/api/v1/recurrentes/{rec['id']}", json={**base, "monto": 1, "proxima_fecha": "2026-03-10", "proxima_fecha_vista": "2026-02-28"}, headers=A).json()
    assert otra["dia_ancla"] == 10 and otra["proxima_fecha"] == "2026-03-10"


def test_eliminar_conserva_las_transacciones_ya_registradas(client):
    rec = _crear(client).json()
    client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar", json={"ocurrencia": "2026-11-05"}, headers=A)
    assert client.delete(f"/api/v1/recurrentes/{rec['id']}", headers=A).status_code == 200
    assert client.get("/api/v1/recurrentes", headers=A).json() == []
    assert len(_transacciones(client)) == 1


# ── INV-001: aislamiento entre usuarios ───────────────────────────────────────

def test_inv001_otro_usuario_no_ve_ni_toca_mis_recurrentes(client):
    rec = _crear(client).json()
    rid = rec["id"]
    assert client.get("/api/v1/recurrentes", headers=B).json() == []
    assert _pendientes(client, headers=B).json() == []
    body = {"tipo": "gasto", "monto": 1, "frecuencia": "mensual", "proxima_fecha": "2026-11-05"}
    assert client.put(f"/api/v1/recurrentes/{rid}", json=body, headers=B).status_code == 404
    assert client.delete(f"/api/v1/recurrentes/{rid}", headers=B).status_code == 404
    assert client.post(f"/api/v1/recurrentes/{rid}/confirmar", json={"ocurrencia": "2026-11-05"}, headers=B).status_code == 404
    assert client.post(f"/api/v1/recurrentes/{rid}/omitir", json={"ocurrencia": "2026-11-05"}, headers=B).status_code == 404
    assert _transacciones(client, headers=B) == []
    # Sigue intacta para su dueño
    assert client.get("/api/v1/recurrentes", headers=A).json()[0]["proxima_fecha"] == "2026-11-05"


def test_sin_sesion_es_rechazado(client):
    assert client.get("/api/v1/recurrentes").status_code == 422
    assert client.get("/api/v1/recurrentes", headers={"Authorization": "Bearer x"}).status_code == 401


# ── INV-025: pendientes y confirmación explícita ─────────────────────────────

def test_inv025_crear_no_registra_ninguna_transaccion(client):
    _crear(client, proxima_fecha="2026-11-01")
    assert _transacciones(client) == []


def test_inv025_pendientes_solo_las_activas_cuya_fecha_llego(client):
    hoy = _crear(client, descripcion="hoy", proxima_fecha="2026-11-23").json()
    vencida = _crear(client, descripcion="vencida", proxima_fecha="2026-11-01").json()
    _crear(client, descripcion="futura", proxima_fecha="2026-11-24")
    _crear(client, descripcion="pausada", proxima_fecha="2026-11-01", activa=False)
    assert [r["id"] for r in _pendientes(client).json()] == [vencida["id"], hoy["id"]]


def test_pendientes_con_fecha_invalida_es_422(client):
    assert _pendientes(client, hasta="2026-02-31").status_code == 422
    assert _pendientes(client, hasta="ayer").status_code == 422


def test_inv025_confirmar_crea_la_transaccion_y_avanza_la_fecha(client):
    cat = client.post("/api/v1/categorias", json={"nombre": "Arriendo", "tipo": "gasto"}, headers=A).json()
    rec = _crear(client, categoria_id=cat["id"]).json()
    r = client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar", json={"ocurrencia": "2026-11-05"}, headers=A)
    assert r.status_code == 200
    tx = r.json()["transaccion"]
    assert (tx["monto"], tx["fecha"], tx["tipo"], tx["categoria_id"], tx["medio_pago"], tx["descripcion"]) == \
        (1_500_000, "2026-11-05", "gasto", cat["id"], "transferencia", "Arriendo")
    assert r.json()["recurrente"]["proxima_fecha"] == "2026-12-05"
    assert _pendientes(client).json() == []


def test_confirmar_con_monto_y_fecha_ajustados(client):
    rec = _crear(client, descripcion="Luz", monto=90_000).json()
    r = client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar",
                    json={"ocurrencia": "2026-11-05", "monto": 104_350.5, "fecha": "2026-11-07"}, headers=A)
    tx = r.json()["transaccion"]
    assert (tx["monto"], tx["fecha"]) == (104_350.5, "2026-11-07")
    # El monto de la plantilla no cambia: el próximo mes vuelve a proponer 90.000
    assert client.get("/api/v1/recurrentes", headers=A).json()[0]["monto"] == 90_000


@pytest.mark.parametrize("cambio", [{"monto": 0}, {"monto": 2e12}, {"fecha": "2026-02-30"}, {"fecha": "hoy"}])
def test_confirmar_con_ajustes_invalidos_no_registra_nada(client, cambio):
    rec = _crear(client).json()
    r = client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar", json={"ocurrencia": "2026-11-05", **cambio}, headers=A)
    assert r.status_code == 422
    assert _transacciones(client) == []
    assert client.get("/api/v1/recurrentes", headers=A).json()[0]["proxima_fecha"] == "2026-11-05"


def test_inv026_doble_confirmacion_registra_una_sola_vez(client):
    rec = _crear(client).json()
    url = f"/api/v1/recurrentes/{rec['id']}/confirmar"
    assert client.post(url, json={"ocurrencia": "2026-11-05"}, headers=A).status_code == 200
    segunda = client.post(url, json={"ocurrencia": "2026-11-05"}, headers=A)
    assert segunda.status_code == 409
    assert len(_transacciones(client)) == 1


def test_inv026_carrera_compare_and_set(client, monkeypatch):
    """Si otra petición movió la fecha entre la lectura y la escritura, no se registra nada.
    CHG-025: la comprobación vive dentro de la función atómica (en demo, `DemoRecurrenteDB.confirmar`); aquí otra petición
    mueve la fecha justo antes de que corra la confirmación."""
    rec = _crear(client).json()
    original = modelos.RecurrenteDB.confirmar

    async def otra_peticion_la_mueve_antes(*args, **kwargs):
        modelos.DemoRecurrenteDB._recurrentes[rec["id"]]["proxima_fecha"] = "2026-12-05"
        return await original(*args, **kwargs)

    monkeypatch.setattr(modelos.RecurrenteDB, "confirmar", staticmethod(otra_peticion_la_mueve_antes))
    r = client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar", json={"ocurrencia": "2026-11-05"}, headers=A)
    assert r.status_code == 409 and _transacciones(client) == []
    assert client.get("/api/v1/recurrentes", headers=A).json()[0]["proxima_fecha"] == "2026-12-05"


def test_varias_ocurrencias_atrasadas_se_confirman_una_por_una(client):
    rec = _crear(client, frecuencia="semanal", proxima_fecha="2026-11-02", descripcion="Mercado").json()
    fechas = []
    for _ in range(4):
        pend = _pendientes(client).json()
        if not pend:
            break
        fechas.append(pend[0]["proxima_fecha"])
        client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar", json={"ocurrencia": pend[0]["proxima_fecha"]}, headers=A)
    assert fechas == ["2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23"]
    assert sorted(t["fecha"] for t in _transacciones(client)) == fechas


def test_omitir_avanza_sin_registrar(client):
    rec = _crear(client).json()
    r = client.post(f"/api/v1/recurrentes/{rec['id']}/omitir", json={"ocurrencia": "2026-11-05"}, headers=A)
    assert r.status_code == 200 and r.json()["proxima_fecha"] == "2026-12-05"
    assert _transacciones(client) == []
    assert client.post(f"/api/v1/recurrentes/{rec['id']}/omitir", json={"ocurrencia": "2026-11-05"}, headers=A).status_code == 409


def test_pausada_no_se_puede_confirmar(client):
    rec = _crear(client, activa=False).json()
    r = client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar", json={"ocurrencia": "2026-11-05"}, headers=A)
    assert r.status_code == 409 and _transacciones(client) == []


def test_si_falla_la_transaccion_la_ocurrencia_sigue_pendiente(client, monkeypatch):
    """CHG-025: confirmar es UNA función atómica. Si falla, la fecha ni siquiera se movió: no hay nada que revertir."""
    rec = _crear(client).json()

    async def falla(*args, **kwargs):
        raise RuntimeError("Supabase caído")

    async def no_debe_usarse(*args, **kwargs):
        raise AssertionError("confirmar ya no avanza la fecha por separado (flujo anterior)")

    monkeypatch.setattr(modelos.RecurrenteDB, "confirmar", staticmethod(falla))
    monkeypatch.setattr(modelos.RecurrenteDB, "avanzar", staticmethod(no_debe_usarse))
    r = client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar", json={"ocurrencia": "2026-11-05"}, headers=A)
    assert r.status_code == 500 and r.json()["detail"] == "No se pudo registrar la transacción"
    assert [p["proxima_fecha"] for p in _pendientes(client).json()] == ["2026-11-05"]


def test_categoria_borrada_la_recurrente_queda_sin_categoria(client):
    cat = client.post("/api/v1/categorias", json={"nombre": "Gym", "tipo": "gasto"}, headers=A).json()
    rec = _crear(client, categoria_id=cat["id"]).json()
    # En Supabase la llave foránea hace SET NULL; en el modo demo se simula aquí
    modelos.DemoRecurrenteDB._recurrentes[rec["id"]]["categoria_id"] = None
    client.delete(f"/api/v1/categorias/{cat['id']}", headers=A)
    r = client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar", json={"ocurrencia": "2026-11-05"}, headers=A)
    assert r.status_code == 200 and r.json()["transaccion"]["categoria_id"] in (None, "")


# ── Revisión CHG-012 (H1, H2): ediciones con datos viejos y fallo de la reversión ──

def test_inv026_editar_con_la_fecha_vieja_no_la_hace_retroceder(client):
    """Escenario del revisor: formulario abierto, se confirma desde pendientes y luego se guarda la edición."""
    rec = _crear(client).json()
    client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar", json={"ocurrencia": "2026-11-05"}, headers=A)
    base = {"tipo": "gasto", "descripcion": "Arriendo", "frecuencia": "mensual", "monto": 1_600_000}
    # Un cliente que reenvía la fecha que tenía cargada como "próxima" sin haberla cambiado
    r = client.put(f"/api/v1/recurrentes/{rec['id']}", json={**base, "proxima_fecha": "2026-11-05", "proxima_fecha_vista": "2026-11-05"}, headers=A)
    assert r.status_code == 409
    # Sin enviar fecha (pausar, editar el monto) la fecha se conserva
    r = client.put(f"/api/v1/recurrentes/{rec['id']}", json={**base, "activa": False}, headers=A)
    assert r.status_code == 200 and r.json()["proxima_fecha"] == "2026-12-05" and r.json()["monto"] == 1_600_000
    r = client.put(f"/api/v1/recurrentes/{rec['id']}", json={**base, "activa": True}, headers=A)
    assert r.json()["proxima_fecha"] == "2026-12-05"
    assert _pendientes(client).json() == [] and len(_transacciones(client)) == 1


def test_cambiar_la_fecha_exige_haber_visto_la_actual(client):
    rec = _crear(client).json()
    base = {"tipo": "gasto", "monto": 1, "frecuencia": "mensual"}
    sin_vista = client.put(f"/api/v1/recurrentes/{rec['id']}", json={**base, "proxima_fecha": "2026-11-10"}, headers=A)
    assert sin_vista.status_code == 409
    ok = client.put(f"/api/v1/recurrentes/{rec['id']}", json={**base, "proxima_fecha": "2026-11-10", "proxima_fecha_vista": "2026-11-05"}, headers=A)
    assert ok.status_code == 200 and ok.json()["proxima_fecha"] == "2026-11-10" and ok.json()["dia_ancla"] == 10
