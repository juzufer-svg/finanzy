"""INV-003, INV-004 e INV-005: validación de montos, tipos y fechas. (BDD-TRANSACCIONES)"""
import pytest

from app.models.plataapp import MetaDB
from conftest import auth_header
from test_cuentas import FILA_CUENTA, INEXISTENTE, _con_supabase_falso, _ErrorPG

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


# ───────────── INV-003: tope de NUMERIC(12,2) y 2 decimales (CHG-029) ─────────────

TOPE = 9999999999.99
MSG_TOPE = "El monto debe tener máximo 2 decimales y no superar $9.999.999.999,99 (pesos colombianos)"


def _meta(client, objetivo=100):
    r = client.post("/api/v1/metas", json={"nombre": "M", "monto_objetivo": objetivo, "fecha_objetivo": "2027-01-01"}, headers=A)
    assert r.status_code == 200, r.text
    return r.json()


def _entradas(client):
    """Cada entrada de la API con montos (sin cuenta de dinero): (nombre, función que envía el valor)."""
    cat = client.post("/api/v1/categorias", json={"nombre": "Tope", "icono": "", "tipo": "gasto"}, headers=A).json()
    tx = client.post("/api/v1/transacciones", json=BASE, headers=A).json()
    pres = client.post("/api/v1/presupuestos", json={"categoria_id": cat["id"], "limite_mensual": 5, "mes_ano": "2026-10"},
                       headers=A).json()
    meta = _meta(client)
    rec_base = {"tipo": "gasto", "monto": 5, "frecuencia": "mensual", "proxima_fecha": "2026-11-22"}
    rec = client.post("/api/v1/recurrentes", json=rec_base, headers=A).json()
    meses = iter(f"{a}-{m:02d}" for a in range(2027, 2030) for m in range(1, 13))

    def confirmar(v):
        actual = next(r for r in client.get("/api/v1/recurrentes", headers=A).json() if r["id"] == rec["id"])
        return client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar",
                           json={"ocurrencia": actual["proxima_fecha"], "monto": v}, headers=A)

    def abonar(v):
        return client.post(f"/api/v1/metas/{_meta(client)['id']}/abonar", json={"monto": v, "fecha": "2026-11-22"}, headers=A)

    return [
        ("transaccion.crear", lambda v: client.post("/api/v1/transacciones", json={**BASE, "monto": v}, headers=A)),
        ("transaccion.editar", lambda v: client.put(f"/api/v1/transacciones/{tx['id']}", json={**BASE, "monto": v}, headers=A)),
        ("presupuesto.crear", lambda v: client.post("/api/v1/presupuestos", json={
            "categoria_id": cat["id"], "limite_mensual": v, "mes_ano": next(meses)}, headers=A)),
        ("presupuesto.editar", lambda v: client.put(f"/api/v1/presupuestos/{pres['id']}", json={"limite_mensual": v}, headers=A)),
        ("meta.crear", lambda v: client.post("/api/v1/metas", json={
            "nombre": "M", "monto_objetivo": v, "fecha_objetivo": "2027-01-01"}, headers=A)),
        ("meta.objetivo", lambda v: client.put(f"/api/v1/metas/{meta['id']}", json={"monto_objetivo": v}, headers=A)),
        ("meta.ahorrado", lambda v: client.put(f"/api/v1/metas/{meta['id']}", json={"monto_actual": v}, headers=A)),
        ("meta.abonar", abonar),
        ("recurrente.crear", lambda v: client.post("/api/v1/recurrentes", json={**rec_base, "monto": v}, headers=A)),
        ("recurrente.editar", lambda v: client.put(f"/api/v1/recurrentes/{rec['id']}", json={
            **{k: x for k, x in rec_base.items() if k != "proxima_fecha"}, "monto": v}, headers=A)),
        ("recurrente.confirmar", confirmar),
    ]


def _estado(client):
    return [client.get(f"/api/v1/{ruta}", headers=A).json()
            for ruta in ("transacciones", "presupuestos/2026-10", "recurrentes")]


def _assert_rechazado(r, nombre, valor):
    assert r.status_code == 422, (nombre, valor, r.text)
    assert r.json()["detail"][0]["msg"] == f"Value error, {MSG_TOPE}", (nombre, valor, r.text)


@pytest.mark.parametrize("monto", [10000000000, 10000000000.0, 1e12, 10**13, "10000000000.00"])
def test_inv003_tope_en_cada_entrada(client, monto):
    entradas = _entradas(client)
    antes = _estado(client)
    for nombre, enviar in entradas:
        _assert_rechazado(enviar(monto), nombre, monto)
    assert _estado(client) == antes


@pytest.mark.parametrize("monto", [12.345, 0.001, 9999999999.989, "1.001"])
def test_inv003_maximo_dos_decimales(client, monto):
    entradas = _entradas(client)
    antes = _estado(client)
    for nombre, enviar in entradas:
        _assert_rechazado(enviar(monto), nombre, monto)
    assert _estado(client) == antes


@pytest.mark.parametrize("monto", [TOPE, 0.01, 0.1, 100.5])
def test_inv003_limites_aceptados(client, monto):
    for nombre, enviar in _entradas(client):
        r = enviar(monto)
        assert r.status_code == 200, (nombre, monto, r.text)


def test_inv003_ahorrado_admite_cero_y_los_montos_siguen_siendo_positivos(client):
    meta = _meta(client)
    assert client.put(f"/api/v1/metas/{meta['id']}", json={"monto_actual": 0}, headers=A).status_code == 200
    assert client.put(f"/api/v1/metas/{meta['id']}", json={"monto_actual": -0.01}, headers=A).status_code == 422
    for nombre, enviar in _entradas(client):
        if nombre != "meta.ahorrado":
            assert enviar(0).status_code == 422, nombre


def test_inv003_con_cuenta_de_dinero_mismo_tope_y_nada_cambia(client):
    cuenta = client.post("/api/v1/cuentas", json={"nombre": "C", "tipo": "efectivo", "saldo_inicial": 1000}, headers=A).json()["id"]
    meta = _meta(client)
    rec = {"tipo": "gasto", "monto": 5, "frecuencia": "mensual", "proxima_fecha": "2026-11-22", "cuenta_id": cuenta}
    r = client.post("/api/v1/recurrentes", json=rec, headers=A).json()
    antes = _foto(client) + _estado(client)
    for malo in (10000000000, 1e12, 10**13, 12.345, 0.001):
        for url, cuerpo in (
            ("transacciones", {**BASE, "monto": malo, "cuenta_id": cuenta}),
            (f"metas/{meta['id']}/abonar", {"monto": malo, "fecha": "2026-11-22", "cuenta_id": cuenta}),
            ("recurrentes", {**rec, "monto": malo}),
            (f"recurrentes/{r['id']}/confirmar", {"ocurrencia": "2026-11-22", "monto": malo, "cuenta_id": cuenta}),
            (f"recurrentes/{r['id']}/confirmar", {"ocurrencia": "2026-11-22", "monto": malo}),
        ):
            assert client.post(f"/api/v1/{url}", json=cuerpo, headers=A).status_code == 422, (url, malo)
    assert _foto(client) + _estado(client) == antes


# ── Abono: el acumulado no puede pasar del tope ──

def _foto(client):
    return [client.get(f"/api/v1/{ruta}", headers=A).json() for ruta in ("metas", "transacciones", "categorias", "cuentas")]


@pytest.mark.parametrize("con_cuenta", [False, True])
def test_inv003_abono_acumulado_422_sin_cambios(client, con_cuenta):
    """Modo demo / sin transacción SQL."""
    cuenta = None
    if con_cuenta:
        cuenta = client.post("/api/v1/cuentas", json={"nombre": "C", "tipo": "efectivo", "saldo_inicial": 1000},
                             headers=A).json()["id"]
    meta = _meta(client)
    assert client.put(f"/api/v1/metas/{meta['id']}", json={"monto_actual": 9999999999.98}, headers=A).status_code == 200
    antes = _foto(client)
    cuerpo = {"monto": 0.02, "fecha": "2026-11-22", "cuenta_id": cuenta}
    r = client.post(f"/api/v1/metas/{meta['id']}/abonar", json=cuerpo, headers=A)
    assert r.status_code == 422 and r.json() == {"detail": MSG_TOPE}, r.text
    assert _foto(client) == antes
    # llegar exactamente al tope sí se permite
    r = client.post(f"/api/v1/metas/{meta['id']}/abonar", json={**cuerpo, "monto": 0.01}, headers=A)
    assert r.status_code == 200 and r.json()["monto_actual"] == TOPE, r.text


def test_inv003_abono_acumulado_sin_error_de_coma_flotante(client):
    meta = _meta(client)
    for monto in (0.1, 0.2):
        r = client.post(f"/api/v1/metas/{meta['id']}/abonar", json={"monto": monto, "fecha": "2026-11-22"}, headers=A)
    assert r.json()["monto_actual"] == 0.3


@pytest.mark.parametrize("con_cuenta", [False, True])
def test_inv003_abono_atomico_desbordado_en_la_bd_responde_422(client, monkeypatch, capsys, con_cuenta):
    """Camino atómico: `abonar_meta` revierte todo y la BD lanza 22003; nunca se usa el método anterior."""
    llamadas = []

    def fuente(q):
        llamadas.append(q.tabla)
        if q.tabla == "rpc:abonar_meta":
            raise _ErrorPG("22003")
        return [FILA_CUENTA] if q.tabla == "cuentas" else []
    cliente = _con_supabase_falso(monkeypatch, fuente)
    cuerpo = {"monto": 5, "fecha": "2026-11-22", "cuenta_id": FILA_CUENTA["id"] if con_cuenta else None}
    r = client.post(f"/api/v1/metas/{INEXISTENTE}/abonar", json=cuerpo, headers=A)
    assert r.status_code == 422 and r.json() == {"detail": MSG_TOPE}, r.text
    assert llamadas.count("rpc:abonar_meta") == 1 and "transacciones" not in llamadas and "metas" not in llamadas
    assert cliente.consultas and "secreto" not in capsys.readouterr().out


def test_inv003_abono_sin_transaccion_desbordado_en_la_bd_revierte_el_gasto(client, monkeypatch):
    """Otro abono llegó a la vez en el método anterior: la BD rechaza la meta (22003), se borra el gasto y es 422."""
    meta = _meta(client)

    async def desborda(*_a, **_k):
        raise _ErrorPG("22003")

    monkeypatch.setattr(MetaDB, "actualizar_progreso", staticmethod(desborda))
    r = client.post(f"/api/v1/metas/{meta['id']}/abonar", json={"monto": 5, "fecha": "2026-11-22"}, headers=A)
    assert r.status_code == 422 and r.json() == {"detail": MSG_TOPE}
    assert client.get("/api/v1/transacciones", headers=A).json() == []
