"""CHG-025 (fase c de CHG-019) · INV-052, INV-046, INV-008, INV-025, INV-026, INV-023, INV-029 · CT-006/007/008/009/011 v1.1.

Integraciones de las cuentas de dinero: abono a metas con cuenta de origen, recurrentes con cuenta y confirmación ATÓMICA
(`confirmar_recurrente`), WhatsApp con cuenta nombrada, asistente de solo lectura (`cuentas_y_saldos`) y columna «Cuenta» en
la exportación.

El modo demo en memoria implementa las MISMAS reglas que las funciones SQL de `backend/sql/2026-11-25_cuentas_integracion.sql`;
la atomicidad y la concurrencia reales se prueban en PostgreSQL (`backend/sql/pruebas/10_comprobar_cuentas_integracion.sql`,
`probar.sh`). Las pruebas con cliente FALSO comprueban la rama de Supabase: una sola llamada a la función, el ejecutor propio de
cuentas, la traducción de errores sin texto de la BD y el 503 sin la función (nunca el método anterior).
"""
import asyncio
import csv
import io
import json
import threading
import uuid

import pytest
from openpyxl import load_workbook

import test_whatsapp as tw
from app.models import plataapp as modelos
from app.models.demo_db import DemoRecurrenteDB, DemoTransaccionDB, DemoTransferenciaDB, ErrorBD
from app.models.plataapp import RecurrenteDB
from app.utils import asistente
from test_cuentas import A, B, FILA_CUENTA, INEXISTENTE, _ErrorPG, _con_supabase_falso, _cuenta, _saldo, _tx

meta = tw.meta   # fixture compartida: WhatsApp configurado y Claude simulado
MSG_SALDO = "Saldo insuficiente en la cuenta: esto la dejaría en negativo. Solo las tarjetas de crédito pueden quedar en negativo."
MSG_ARCHIVADA = "La cuenta está archivada. Desarchívala para registrar movimientos."
MSG_OCURRENCIA = "Esta fecha ya se registró u omitió. Actualiza la lista de pendientes."
ABONO = {"monto": 30000, "fecha": "2026-11-22", "descripcion": "Para el viaje"}


# ───────────── Ayudas ─────────────

def _meta(client, h=A, objetivo=1_000_000):
    r = client.post("/api/v1/metas", json={"nombre": "Viaje", "monto_objetivo": objetivo, "fecha_objetivo": "2027-06-01"}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _meta_actual(client, meta_id, h=A):
    return next(m for m in client.get("/api/v1/metas", headers=h).json() if m["id"] == meta_id)["monto_actual"]


def _abonar(client, meta_id, h=A, **extra):
    return client.post(f"/api/v1/metas/{meta_id}/abonar", json={**ABONO, **extra}, headers=h)


def _txs(client, h=A):
    return client.get("/api/v1/transacciones", headers=h).json()


def _recurrente(client, h=A, esperado=200, **extra):
    body = {"tipo": "gasto", "monto": 20000, "descripcion": "Arriendo", "frecuencia": "mensual",
            "proxima_fecha": "2026-11-05", **extra}
    r = client.post("/api/v1/recurrentes", json=body, headers=h)
    assert r.status_code == esperado, r.text
    return r.json()


def _confirmar(client, rec, h=A, ocurrencia="2026-11-05", **extra):
    return client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar", json={"ocurrencia": ocurrencia, **extra}, headers=h)


def _fecha_de(client, rec, h=A):
    return next(r for r in client.get("/api/v1/recurrentes", headers=h).json() if r["id"] == rec["id"])["proxima_fecha"]


# ───────────── Abono a meta con cuenta de origen (INV-052, INV-008) ─────────────

def test_inv052_abono_a_meta_con_cuenta_descuenta_el_saldo(client):
    ahorros = _cuenta(client, "Ahorros", "ahorros_corriente", 100000)
    m = _meta(client)
    r = _abonar(client, m["id"], cuenta_id=ahorros["id"])
    assert r.status_code == 200, r.text
    assert r.json()["monto_actual"] == 30000 and r.json()["porcentaje_completado"] == 3
    gasto = _txs(client)
    assert len(gasto) == 1 and gasto[0]["tipo"] == "gasto" and gasto[0]["monto"] == 30000
    assert gasto[0]["cuenta_id"] == ahorros["id"]
    ahorro = next(c for c in client.get("/api/v1/categorias", headers=A).json() if c["nombre"] == "Ahorro")
    assert gasto[0]["categoria_id"] == ahorro["id"]
    assert _saldo(client, ahorros) == 70000
    # Sin cuenta todo sigue igual que antes: gasto sin cuenta y ningún saldo cambia
    assert _abonar(client, m["id"], monto=1000).status_code == 200
    assert _saldo(client, ahorros) == 70000 and _txs(client)[-1].get("cuenta_id") is None


def test_inv052_abono_con_saldo_insuficiente_no_suma_a_la_meta_ni_registra_gasto(client):
    efectivo = _cuenta(client, "Efectivo", "efectivo", 10000)
    m = _meta(client)
    r = _abonar(client, m["id"], cuenta_id=efectivo["id"])
    assert r.status_code == 409 and r.json()["detail"] == MSG_SALDO
    assert _meta_actual(client, m["id"]) == 0                                    # INV-008: la meta no cambió
    assert _txs(client) == []                                                    # ni se registró el gasto
    assert "Ahorro" not in [c["nombre"] for c in client.get("/api/v1/categorias", headers=A).json()]   # ni la categoría
    assert _saldo(client, efectivo) == 10000
    # Cuenta archivada: 409 con su mensaje y tampoco cambia nada
    assert client.put(f"/api/v1/cuentas/{efectivo['id']}", json={"archivada": True}, headers=A).status_code == 200
    r = _abonar(client, m["id"], monto=1000, cuenta_id=efectivo["id"])
    assert r.status_code == 409 and r.json()["detail"] == MSG_ARCHIVADA
    assert _meta_actual(client, m["id"]) == 0 and _txs(client) == []
    # El monto con cuenta respeta el tope y los 2 decimales (INV-051): 422, nunca error de la BD
    otra = _cuenta(client, "Otra", "efectivo", 1000)
    assert _abonar(client, m["id"], monto=10.123, cuenta_id=otra["id"]).status_code == 422
    # Meta ajena o inexistente con una cuenta propia: 404 y el saldo no cambia
    assert _abonar(client, str(uuid.uuid4()), monto=500, cuenta_id=otra["id"]).status_code == 404
    assert _saldo(client, otra) == 1000


def test_inv052_abono_con_cuenta_ajena_404_y_sin_funcion_sql_responde_503(client, monkeypatch):
    # 1) Cuenta de otro usuario: 404 «Cuenta no encontrada» y nada cambia (INV-046)
    ajena = _cuenta(client, "Secreta", "efectivo", 50000, h=B)
    m = _meta(client)
    r = _abonar(client, m["id"], cuenta_id=ajena["id"])
    assert r.status_code == 404 and r.json()["detail"] == "Cuenta no encontrada"
    assert _meta_actual(client, m["id"]) == 0 and _txs(client) == [] and _saldo(client, ajena, B) == 50000
    assert _abonar(client, m["id"], cuenta_id=INEXISTENTE).status_code == 404
    assert _abonar(client, m["id"], cuenta_id="no-es-uuid").status_code == 422

    # 2) Con cuenta y SIN la función SQL nueva: 503 y NUNCA el método anterior (no atómico)
    def fuente(q):
        if q.tabla == "cuentas" and q.valor("select"):
            return [FILA_CUENTA]
        if q.tabla == "rpc:abonar_meta":
            raise _ErrorPG("PGRST202", "Could not find the function public.abonar_meta(p_cuenta_id) secreto-de-la-bd")
        raise AssertionError(f"consulta inesperada a {q.tabla}")

    async def no_debe_usarse(*_a, **_k):
        raise AssertionError("no se debe usar el método anterior no atómico con cuenta")

    cliente = _con_supabase_falso(monkeypatch, fuente)
    monkeypatch.setattr(modelos.TransaccionDB, "crear", staticmethod(no_debe_usarse))
    monkeypatch.setattr(modelos.MetaDB, "actualizar_progreso", staticmethod(no_debe_usarse))
    for codigo in ("PGRST202", "42883"):
        cliente.consultas.clear()
        cliente.fuente = lambda q, c=codigo: ([FILA_CUENTA] if q.tabla == "cuentas" else (_ for _ in ()).throw(_ErrorPG(c)))
        r = _abonar(client, str(uuid.uuid4()), cuenta_id=INEXISTENTE)
        assert r.status_code == 503 and "secreto-de-la-bd" not in r.text
        assert [q.tabla for q in cliente.consultas].count("rpc:abonar_meta") == 1
        assert not any(q.tabla in ("transacciones", "metas") for q in cliente.consultas)


def test_inv052_abono_con_cuenta_usa_la_funcion_del_ejecutor_de_cuentas_y_traduce_errores(client, monkeypatch):
    hilos = []
    META = {"id": "m1", "usuario_id": "user-a", "nombre": "Viaje", "monto_objetivo": 200, "monto_actual": 30,
            "fecha_objetivo": "2027-01-01"}
    resultado = {"v": [META]}

    def fuente(q):
        if q.tabla == "cuentas":
            return [FILA_CUENTA]
        hilos.append(threading.current_thread().name)
        if isinstance(resultado["v"], Exception):
            raise resultado["v"]
        return resultado["v"]

    cliente = _con_supabase_falso(monkeypatch, fuente)
    r = _abonar(client, "m1", cuenta_id=INEXISTENTE)
    assert r.status_code == 200 and r.json()["porcentaje_completado"] == 15
    rpc = [q for q in cliente.consultas if q.tabla == "rpc:abonar_meta"][0]
    assert rpc.args == {"p_meta_id": "m1", "p_usuario_id": "user-a", "p_monto": 30000, "p_fecha": "2026-11-22",
                        "p_descripcion": "Para el viaje", "p_cuenta_id": INEXISTENTE}
    assert hilos and all(h.startswith("cuentas") and "auth-estado" not in h for h in hilos)   # ejecutor propio (ADR-009 p.14)
    esperado = [("FZ001", 409, MSG_SALDO), ("FZ002", 409, MSG_ARCHIVADA), ("23503", 404, "Cuenta no encontrada"),
                ("P0002", 404, "Meta no encontrada"), ("22003", 422, None), ("57014", 503, None), ("XX000", 503, None)]
    for codigo, status, detalle in esperado:
        resultado["v"] = _ErrorPG(codigo)
        r = _abonar(client, "m1", cuenta_id=INEXISTENTE)
        assert r.status_code == status and "secreto-de-la-bd" not in r.text, (codigo, r.text)
        if detalle:
            assert r.json()["detail"] == detalle


# ───────────── Recurrentes con cuenta (INV-046, INV-052) ─────────────

def test_inv051_recurrente_con_cuenta_valida_el_tope_al_crear_y_editar_422(client):
    efectivo = _cuenta(client, "Efectivo", "efectivo", 1000)
    for monto in (10_000_000_000, 5.123):
        r = client.post("/api/v1/recurrentes", json={"tipo": "gasto", "monto": monto, "frecuencia": "mensual",
                                                     "proxima_fecha": "2026-11-05", "cuenta_id": efectivo["id"]}, headers=A)
        assert r.status_code == 422, r.text
    assert client.get("/api/v1/recurrentes", headers=A).json() == []
    # Sin cuenta rige el mismo tope (INV-003, CHG-029)
    _recurrente(client, monto=10_000_000_000, esperado=422)
    sin = _recurrente(client, monto=9999999999.99)
    base = {"tipo": "gasto", "descripcion": "Arriendo", "frecuencia": "mensual"}
    # Editar para quedar CON cuenta: 422 y no cambia nada
    r = client.put(f"/api/v1/recurrentes/{sin['id']}", json={**base, "monto": 10_000_000_000, "cuenta_id": efectivo["id"]}, headers=A)
    assert r.status_code == 422, r.text
    assert client.get("/api/v1/recurrentes", headers=A).json()[0].get("cuenta_id") is None
    # Editar el monto de una que YA tiene cuenta (sin reenviar cuenta_id) también valida
    con = _recurrente(client, cuenta_id=efectivo["id"])
    assert client.put(f"/api/v1/recurrentes/{con['id']}", json={**base, "monto": 5.123}, headers=A).status_code == 422
    assert client.put(f"/api/v1/recurrentes/{con['id']}", json={**base, "monto": 7.5}, headers=A).status_code == 200
    # Quitar la cuenta no levanta el tope (INV-003)
    assert client.put(f"/api/v1/recurrentes/{con['id']}", json={**base, "monto": 10_000_000_000, "cuenta_id": None}, headers=A).status_code == 422
    assert client.put(f"/api/v1/recurrentes/{con['id']}", json={**base, "monto": 9999999999.99, "cuenta_id": None}, headers=A).status_code == 200



def test_inv046_recurrente_con_cuenta_ajena_404_crear_editar_y_confirmar(client):
    ajena = _cuenta(client, "Secreta", "efectivo", 50000, h=B)
    # Crear con la cuenta de B: 404 y no se guarda nada
    r = client.post("/api/v1/recurrentes", json={"tipo": "gasto", "monto": 1000, "frecuencia": "mensual",
                                                 "proxima_fecha": "2026-11-05", "cuenta_id": ajena["id"]}, headers=A)
    assert r.status_code == 404 and r.json()["detail"] == "Cuenta no encontrada"
    assert client.get("/api/v1/recurrentes", headers=A).json() == []
    # Editar una propia con la cuenta de B: 404 y no cambia nada
    rec = _recurrente(client)
    base = {"tipo": "gasto", "monto": 1000, "descripcion": "Arriendo", "frecuencia": "mensual"}
    assert client.put(f"/api/v1/recurrentes/{rec['id']}", json={**base, "cuenta_id": ajena["id"]}, headers=A).status_code == 404
    assert client.get("/api/v1/recurrentes", headers=A).json()[0]["monto"] == 20000
    assert client.get("/api/v1/recurrentes", headers=A).json()[0].get("cuenta_id") is None
    # Confirmar una propia con la cuenta de B: 404, no hay transacción, no se toca el saldo de B y la fecha NO avanza
    r = _confirmar(client, rec, cuenta_id=ajena["id"])
    assert r.status_code == 404 and r.json()["detail"] == "Cuenta no encontrada"
    assert _txs(client) == [] and _txs(client, B) == [] and _saldo(client, ajena, B) == 50000
    assert _fecha_de(client, rec) == "2026-11-05"
    # Un id que no es UUID se rechaza con 422 en los tres casos
    assert client.post("/api/v1/recurrentes", json={"tipo": "gasto", "monto": 1, "frecuencia": "mensual",
                                                    "proxima_fecha": "2026-11-05", "cuenta_id": "x"}, headers=A).status_code == 422
    assert _confirmar(client, rec, cuenta_id="x").status_code == 422


def test_inv052_recurrente_con_cuenta_crea_la_transaccion_en_esa_cuenta(client):
    efectivo = _cuenta(client, "Efectivo", "efectivo", 100000)
    otra = _cuenta(client, "Banco", "ahorros_corriente", 50000)
    rec = _recurrente(client, cuenta_id=efectivo["id"])
    assert rec["cuenta_id"] == efectivo["id"] and _txs(client) == []             # crear no registra nada (INV-025)
    r = _confirmar(client, rec)                                                  # sin enviar cuenta: usa la de la plantilla
    assert r.status_code == 200, r.text
    assert r.json()["transaccion"]["cuenta_id"] == efectivo["id"] and r.json()["transaccion"]["monto"] == 20000
    assert r.json()["recurrente"]["proxima_fecha"] == "2026-12-05" and r.json()["recurrente"]["cuenta_id"] == efectivo["id"]
    assert _saldo(client, efectivo) == 80000 and _fecha_de(client, rec) == "2026-12-05"
    # Reemplazar la cuenta al confirmar
    r = _confirmar(client, rec, ocurrencia="2026-12-05", cuenta_id=otra["id"], monto=5000)
    assert r.status_code == 200 and r.json()["transaccion"]["cuenta_id"] == otra["id"]
    assert (_saldo(client, efectivo), _saldo(client, otra)) == (80000, 45000)
    # `null` = sin cuenta (no se envía lo mismo que no mandarla): la transacción queda sin cuenta
    r = _confirmar(client, rec, ocurrencia="2027-01-05", cuenta_id=None)
    assert r.status_code == 200 and r.json()["transaccion"]["cuenta_id"] is None
    assert (_saldo(client, efectivo), _saldo(client, otra)) == (80000, 45000)
    # Editar: no enviar la cuenta la conserva; `null` la quita; un valor la reemplaza
    base = {"tipo": "gasto", "monto": 20000, "descripcion": "Arriendo", "frecuencia": "mensual"}
    assert client.put(f"/api/v1/recurrentes/{rec['id']}", json={**base, "activa": False}, headers=A).json()["cuenta_id"] == efectivo["id"]
    assert client.put(f"/api/v1/recurrentes/{rec['id']}", json={**base, "cuenta_id": otra["id"]}, headers=A).json()["cuenta_id"] == otra["id"]
    assert client.put(f"/api/v1/recurrentes/{rec['id']}", json={**base, "cuenta_id": None}, headers=A).json()["cuenta_id"] is None


def test_inv052_recurrente_con_cuenta_archivada_o_sin_saldo_no_avanza(client):
    efectivo = _cuenta(client, "Efectivo", "efectivo", 10000)
    rec = _recurrente(client, cuenta_id=efectivo["id"], monto=20000)             # el saldo no alcanza
    r = _confirmar(client, rec)
    assert r.status_code == 409 and r.json()["detail"] == MSG_SALDO and "FZ001" not in r.text
    assert _txs(client) == [] and _fecha_de(client, rec) == "2026-11-05" and _saldo(client, efectivo) == 10000
    assert [p["id"] for p in client.get("/api/v1/recurrentes/pendientes?hasta=2026-11-23", headers=A).json()] == [rec["id"]]
    # Cuenta archivada después de crear la recurrente
    assert client.put(f"/api/v1/cuentas/{efectivo['id']}", json={"archivada": True}, headers=A).status_code == 200
    r = _confirmar(client, rec, monto=100)
    assert r.status_code == 409 and r.json()["detail"] == MSG_ARCHIVADA
    assert _txs(client) == [] and _fecha_de(client, rec) == "2026-11-05"
    # Confirmar sin cuenta (null) sí se puede: la archivada no estorba
    assert _confirmar(client, rec, cuenta_id=None).status_code == 200 and _fecha_de(client, rec) == "2026-12-05"
    # Crear o cambiar una recurrente hacia una cuenta archivada: 409; re-enviar la misma al editar no bloquea
    r = client.post("/api/v1/recurrentes", json={"tipo": "gasto", "monto": 1, "frecuencia": "mensual",
                                                 "proxima_fecha": "2026-11-05", "cuenta_id": efectivo["id"]}, headers=A)
    assert r.status_code == 409 and r.json()["detail"] == MSG_ARCHIVADA
    base = {"tipo": "gasto", "monto": 20000, "descripcion": "Arriendo", "frecuencia": "mensual", "cuenta_id": efectivo["id"]}
    assert client.put(f"/api/v1/recurrentes/{rec['id']}", json={**base, "activa": False}, headers=A).status_code == 200
    # Una recurrente de ingreso en una cuenta archivada tampoco se registra
    assert client.put(f"/api/v1/cuentas/{efectivo['id']}", json={"archivada": False}, headers=A).status_code == 200
    # Con cuenta, el monto de la plantilla también respeta el tope y los 2 decimales (INV-051)
    # (crear con cuenta ya lo rechaza; se parte de una plantilla guardada sin cuenta y se confirma con cuenta)
    rec2 = _recurrente(client)
    DemoRecurrenteDB._recurrentes[rec2["id"]]["monto"] = 10.123   # dato imposible por la API: guardado a mano
    assert _confirmar(client, rec2, cuenta_id=efectivo["id"]).status_code == 422 and _fecha_de(client, rec2) == "2026-11-05"


def _fuente_recurrente(registro, rpc):
    """Fuente del cliente falso: la recurrente (lectura previa) y la respuesta de `confirmar_recurrente`."""
    def fuente(q):
        if q.tabla == "recurrentes" and q.valor("select"):
            return [registro]
        if q.tabla == "cuentas" and q.valor("select"):
            return [FILA_CUENTA]
        if q.tabla == "rpc:confirmar_recurrente":
            if isinstance(rpc["v"], Exception):
                raise rpc["v"]
            return rpc["v"]
        raise AssertionError(f"consulta inesperada: {q.tabla} {[n for n, _ in q.llamadas]}")
    return fuente


REGISTRO = {"id": INEXISTENTE, "usuario_id": "user-a", "categoria_id": None, "tipo": "gasto", "monto": 20000,
            "descripcion": "Arriendo", "medio_pago": None, "cuenta_id": None, "frecuencia": "mensual", "dia_ancla": 5,
            "proxima_fecha": "2026-11-05", "activa": True}
TRANSACCION = {"id": "22222222-2222-4222-8222-222222222222", "usuario_id": "user-a", "categoria_id": None, "monto": 20000,
               "descripcion": "Arriendo", "fecha": "2026-11-05", "tipo": "gasto", "medio_pago": None, "cuenta_id": None}


def test_inv052_confirmar_recurrente_es_una_sola_operacion_atomica_y_no_avanza_si_falla(client, monkeypatch):
    rpc = {"v": [TRANSACCION]}
    hilos = []
    fuente_base = _fuente_recurrente(REGISTRO, rpc)

    def fuente(q):
        if q.tabla.startswith("rpc:"):
            hilos.append(threading.current_thread().name)
        return fuente_base(q)

    async def no_debe_usarse(*_a, **_k):
        raise AssertionError("el flujo anterior (avanzar, crear y revertir) ya no existe")

    cliente = _con_supabase_falso(monkeypatch, fuente)
    monkeypatch.setattr(modelos.TransaccionDB, "crear", staticmethod(no_debe_usarse))
    monkeypatch.setattr(modelos.RecurrenteDB, "avanzar", staticmethod(no_debe_usarse))
    url = f"/api/v1/recurrentes/{INEXISTENTE}/confirmar"

    # Camino feliz: UNA llamada a la función SQL (con la fecha siguiente calculada en Python) y ninguna escritura suelta
    r = client.post(url, json={"ocurrencia": "2026-11-05", "monto": 25000.5, "fecha": "2026-11-07"}, headers=A)
    assert r.status_code == 200, r.text
    assert r.json()["transaccion"]["id"] == TRANSACCION["id"] and r.json()["recurrente"]["proxima_fecha"] == "2026-12-05"
    llamadas = [q for q in cliente.consultas if q.tabla.startswith("rpc:")]
    assert [q.tabla for q in llamadas] == ["rpc:confirmar_recurrente"]
    assert llamadas[0].args == {"p_usuario_id": "user-a", "p_recurrente_id": INEXISTENTE, "p_ocurrencia": "2026-11-05",
                                "p_siguiente": "2026-12-05", "p_monto": 25000.5, "p_fecha": "2026-11-07",
                                "p_cuenta_id": None, "p_cuenta_indicada": False}
    assert not any(q.valor("update") or q.valor("insert") or q.valor("delete") for q in cliente.consultas)
    assert hilos and all(h.startswith("cuentas") and "auth-estado" not in h for h in hilos)   # ejecutor propio de cuentas

    # `cuenta_id` enviado (también null) se indica con p_cuenta_indicada = true
    cliente.consultas.clear()
    assert client.post(url, json={"ocurrencia": "2026-11-05", "cuenta_id": None}, headers=A).status_code == 200
    assert client.post(url, json={"ocurrencia": "2026-11-05", "cuenta_id": INEXISTENTE}, headers=A).status_code == 200
    args = [q.args for q in cliente.consultas if q.tabla == "rpc:confirmar_recurrente"]
    assert [(a["p_cuenta_id"], a["p_cuenta_indicada"], a["p_monto"], a["p_fecha"]) for a in args] == [
        (None, True, None, None), (INEXISTENTE, True, None, None)]

    # Si la BD rechaza la confirmación, la ruta responde sin texto de la BD y NO escribe nada más (la fecha no se mueve)
    esperado = [("FZ001", 409, MSG_SALDO), ("FZ002", 409, MSG_ARCHIVADA), ("23503", 404, "Cuenta no encontrada"),
                ("22003", 422, None), ("22023", 422, None), ("P0002", 404, "Recurrente no encontrada"),
                ("57014", 503, None), ("XX000", 503, None)]
    for codigo, status, detalle in esperado:
        cliente.consultas.clear()
        rpc["v"] = _ErrorPG(codigo)
        r = client.post(url, json={"ocurrencia": "2026-11-05"}, headers=A)
        assert r.status_code == status and "secreto-de-la-bd" not in r.text, (codigo, r.text)
        if detalle:
            assert r.json()["detail"] == detalle
        assert not any(q.valor("update") or q.valor("insert") or q.valor("delete") for q in cliente.consultas)
    # ocurrencia_cambiada (pausada o fecha movida entre la lectura y la función): 409 con el mensaje de siempre
    rpc["v"] = _ErrorPG("P0001", "ocurrencia_cambiada")
    r = client.post(url, json={"ocurrencia": "2026-11-05"}, headers=A)
    assert r.status_code == 409 and r.json()["detail"] == MSG_OCURRENCIA
    # Un P0001 con otro texto NO es «ocurrencia cambiada»: no se confunde (503 genérico)
    rpc["v"] = _ErrorPG("P0001", "otra cosa")
    assert client.post(url, json={"ocurrencia": "2026-11-05"}, headers=A).status_code == 503
    # Respuesta inesperada de la función: 503, no un 200 con basura
    for mala in ([], [TRANSACCION, TRANSACCION], [{**TRANSACCION, "usuario_id": "user-b"}], "x"):
        rpc["v"] = mala
        assert client.post(url, json={"ocurrencia": "2026-11-05"}, headers=A).status_code == 503
    # La lectura previa conserva los mensajes de siempre sin llamar a la función
    cliente.consultas.clear()
    pausada = {**REGISTRO, "activa": False}
    cliente.fuente = _fuente_recurrente(pausada, rpc)
    r = client.post(url, json={"ocurrencia": "2026-11-05"}, headers=A)
    assert r.status_code == 409 and r.json()["detail"] == "La recurrente está pausada"
    cliente.fuente = _fuente_recurrente(REGISTRO, rpc)
    r = client.post(url, json={"ocurrencia": "2026-10-05"}, headers=A)
    assert r.status_code == 409 and r.json()["detail"] == MSG_OCURRENCIA
    assert not any(q.tabla.startswith("rpc:") for q in cliente.consultas)


def test_inv052_doble_confirmacion_solo_crea_una_transaccion(client):
    efectivo = _cuenta(client, "Efectivo", "efectivo", 100000)
    rec = _recurrente(client, cuenta_id=efectivo["id"])
    # Dos confirmaciones SIMULTÁNEAS de la misma ocurrencia (bajo el mismo bloqueo): una gana y la otra recibe ocurrencia_cambiada
    async def dos():
        return await asyncio.gather(
            *[RecurrenteDB.confirmar("user-a", rec["id"], "2026-11-05", "2026-12-05", None, None, None, False) for _ in range(2)],
            return_exceptions=True)
    resultados = asyncio.run(dos())
    ganadoras = [x for x in resultados if isinstance(x, dict)]
    perdedoras = [x for x in resultados if isinstance(x, ErrorBD)]
    assert len(ganadoras) == 1 and len(perdedoras) == 1 and perdedoras[0].code == "OCURRENCIA_CAMBIADA"
    assert len(DemoTransaccionDB._transacciones) == 1 and _saldo(client, efectivo) == 80000
    # Y por la API, en dos hilos a la vez y luego un tercer toque: exactamente un 200
    rec2 = _recurrente(client, cuenta_id=efectivo["id"], descripcion="Luz")
    from fastapi.testclient import TestClient
    from app.main import app
    estados, barrera = [], threading.Barrier(2)

    def toque():
        barrera.wait()
        estados.append(_confirmar(TestClient(app), rec2).status_code)

    hilos = [threading.Thread(target=toque) for _ in range(2)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sorted(estados) == [200, 409]
    assert _confirmar(client, rec2).status_code == 409
    assert len(_txs(client)) == 2 and _saldo(client, efectivo) == 60000 and _fecha_de(client, rec2) == "2026-12-05"


def test_inv052_confirmar_sin_la_funcion_sql_responde_503_y_no_usa_el_metodo_anterior(client, monkeypatch):
    rpc = {"v": _ErrorPG("PGRST202", "Could not find the function public.confirmar_recurrente secreto-de-la-bd")}

    async def no_debe_usarse(*_a, **_k):
        raise AssertionError("no se debe usar el flujo anterior (avanzar y luego crear)")

    cliente = _con_supabase_falso(monkeypatch, _fuente_recurrente(REGISTRO, rpc))
    monkeypatch.setattr(modelos.TransaccionDB, "crear", staticmethod(no_debe_usarse))
    monkeypatch.setattr(modelos.RecurrenteDB, "avanzar", staticmethod(no_debe_usarse))
    for codigo in ("PGRST202", "42883"):
        cliente.consultas.clear()
        rpc["v"] = _ErrorPG(codigo, "secreto-de-la-bd")
        r = client.post(f"/api/v1/recurrentes/{INEXISTENTE}/confirmar", json={"ocurrencia": "2026-11-05"}, headers=A)
        assert r.status_code == 503 and "secreto-de-la-bd" not in r.text
        assert not any(q.valor("update") or q.valor("insert") for q in cliente.consultas)   # la fecha no se movió
        assert not any(q.tabla == "transacciones" for q in cliente.consultas)
    # Omitir NO cambia: sigue con su compare-and-set (RecurrenteDB.avanzar)
    assert hasattr(RecurrenteDB, "avanzar")


# ───────────── WhatsApp con cuenta nombrada (INV-029, INV-052) ─────────────

def _registrar(meta, mov):
    meta["claude"].append(tw.herramienta("registrar_movimientos", {"movimientos": mov if isinstance(mov, list) else [mov]}))


def _gasto(monto, **extra):
    return {"tipo": "gasto", "monto": monto, "fecha": "2026-11-23", "medio_pago": "debito", **extra}


def _texto_enviado(meta):
    return meta["enviados"][-1][1]


def test_inv052_whatsapp_cuenta_solo_si_el_usuario_la_nombra(client, meta):
    tw._enlazar(client, meta)
    ahorros = _cuenta(client, "Ahorros", "ahorros_corriente", 100000)
    nomina = _cuenta(client, "Nómina", "ahorros_corriente", 50000)
    _registrar(meta, _gasto(18000, descripcion="Almuerzo", cuenta="Ahorros"))
    tw._msg(client, "almorcé 18 mil con débito desde Ahorros")
    assert _texto_enviado(meta).startswith("✅ Gasto registrado") and "cuenta Ahorros" in _texto_enviado(meta)
    t = tw._tx(client)
    assert len(t) == 1 and t[0]["cuenta_id"] == ahorros["id"] and t[0]["monto"] == 18000
    assert _saldo(client, ahorros) == 82000
    # Sin distinguir mayúsculas ni tildes (ni espacios de más)
    _registrar(meta, _gasto(5000, cuenta="nomina"))
    tw._msg(client, "pagué 5 mil desde NOMINA")
    assert [x["cuenta_id"] for x in tw._tx(client)].count(nomina["id"]) == 1 and _saldo(client, nomina) == 45000
    # Varios movimientos en un mensaje: cada uno con su cuenta
    _registrar(meta, [_gasto(1000, cuenta="Ahorros"), _gasto(2000), {"tipo": "ingreso", "monto": 7000, "fecha": "2026-11-23", "cuenta": "Nómina"}])
    tw._msg(client, "1000 desde ahorros, 2000 de bus y me pagaron 7000 en la nómina")
    assert (_saldo(client, ahorros), _saldo(client, nomina)) == (81000, 52000)


def test_inv052_whatsapp_sin_cuenta_nombrada_registra_sin_cuenta(client, meta):
    tw._enlazar(client, meta)
    ahorros = _cuenta(client, "Ahorros", "ahorros_corriente", 100000)
    _registrar(meta, _gasto(18000, cuenta="Ahorros"))   # la IA la propone pero la persona NO la nombró
    tw._msg(client, "almorcé 18 mil con débito")
    t = tw._tx(client)
    assert _texto_enviado(meta).startswith("✅ Gasto registrado") and len(t) == 1 and t[0].get("cuenta_id") is None
    assert _saldo(client, ahorros) == 100000
    # Campo vacío o con basura: igual, sin cuenta
    for valor in ("", "   ", None, 7, ["Ahorros"]):
        _registrar(meta, _gasto(1000, cuenta=valor))
        tw._msg(client, "gasté mil")
    assert all(x.get("cuenta_id") is None for x in tw._tx(client)) and len(tw._tx(client)) == 6


def test_inv052_whatsapp_cuenta_inexistente_o_sin_saldo_no_registra(client, meta):
    tw._enlazar(client, meta)
    efectivo = _cuenta(client, "Efectivo", "efectivo", 10000)
    vieja = _cuenta(client, "Vieja", "efectivo", 90000)
    assert client.put(f"/api/v1/cuentas/{vieja['id']}", json={"archivada": True}, headers=A).status_code == 200
    secreta = _cuenta(client, "Secreta", "efectivo", 70000, h=B)
    no_existe = "No encontré la cuenta «{}»; escribe el nombre exacto o registra sin cuenta"

    # Inexistente, archivada o de otra persona: el mismo mensaje, sin revelar nada, y no se registra
    for nombre in ("Nequi", "Vieja", "Secreta"):
        _registrar(meta, _gasto(5000, cuenta=nombre))
        tw._msg(client, f"pagué 5 mil desde {nombre}")
        assert _texto_enviado(meta) == no_existe.format(nombre)
        assert tw._tx(client) == []
    assert _saldo(client, vieja) == 90000 and _saldo(client, secreta, B) == 70000 and tw._tx(client, B) == []

    # Sin saldo suficiente: mensaje fijo, sin datos de la BD, nada registrado y el saldo igual
    _registrar(meta, _gasto(30000, cuenta="Efectivo"))
    tw._msg(client, "pagué 30 mil desde Efectivo")
    texto = _texto_enviado(meta)
    assert texto.startswith("No registré nada: la cuenta «Efectivo» no tiene saldo suficiente")
    assert "FZ001" not in texto and "10000" not in texto and tw._tx(client) == [] and _saldo(client, efectivo) == 10000

    # Todo o nada: el primer movimiento cabe, el segundo no → no queda ninguno
    _registrar(meta, [_gasto(4000, cuenta="Efectivo"), _gasto(8000, cuenta="Efectivo")])
    tw._msg(client, "4 mil y 8 mil desde Efectivo")
    assert _texto_enviado(meta).startswith("No registré nada: la cuenta «Efectivo» no tiene saldo suficiente")
    assert tw._tx(client) == [] and _saldo(client, efectivo) == 10000
    # Si uno de varios nombra una cuenta que no existe, tampoco se registra el que sí estaba bien
    _registrar(meta, [_gasto(1000), _gasto(2000, cuenta="Nequi")])
    tw._msg(client, "mil de bus y 2000 desde Nequi")
    assert _texto_enviado(meta) == no_existe.format("Nequi") and tw._tx(client) == []

    # Cuenta archivada JUSTO al registrar (la BD la rechaza con FZ002): mensaje fijo y nada registrado
    original = modelos.TransaccionDB.crear

    async def archivada(*_a, **_k):
        raise ErrorBD("FZ002")
    modelos.TransaccionDB.crear = staticmethod(archivada)
    try:
        _registrar(meta, _gasto(1000, cuenta="Efectivo"))
        tw._msg(client, "mil desde Efectivo")
    finally:
        modelos.TransaccionDB.crear = original
    assert _texto_enviado(meta).startswith("No registré nada: la cuenta «Efectivo» está archivada") and tw._tx(client) == []


def test_whatsapp_monto_fuera_de_lo_permitido_con_cuenta_da_mensaje_fijo_claro(client, meta):
    """23514 y 22003 con cuenta nombrada: mensaje fijo (no «error del servidor») y sin datos de la BD."""
    tw._enlazar(client, meta)
    _cuenta(client, "Efectivo", "efectivo", 10000)
    original = modelos.TransaccionDB.crear
    try:
        for codigo, fragmento in (("23514", "monto no cumple"), ("22003", "demasiado grande")):
            async def rota(*_a, _c=codigo, **_k):
                raise ErrorBD(_c)
            modelos.TransaccionDB.crear = staticmethod(rota)
            _registrar(meta, _gasto(1000, cuenta="Efectivo"))
            tw._msg(client, "mil desde Efectivo")
            texto = _texto_enviado(meta)
            assert fragmento in texto and "error del servidor" not in texto and codigo not in texto, texto
            assert tw._tx(client) == []
    finally:
        modelos.TransaccionDB.crear = original


def test_inv052_whatsapp_no_envia_saldos_ni_ids_a_claude(client, meta):
    tw._enlazar(client, meta)
    ahorros = _cuenta(client, "Ahorros", "ahorros_corriente", 4242424)
    vieja = _cuenta(client, "Vieja", "efectivo", 7373737)
    assert client.put(f"/api/v1/cuentas/{vieja['id']}", json={"archivada": True}, headers=A).status_code == 200
    _cuenta(client, "Secreta", "efectivo", 5151515, h=B)
    meta["claude"].append(tw.texto_claude("Hola"))
    tw._msg(client, "hola")
    payload = json.dumps(meta["payloads"][-1], ensure_ascii=False)
    assert "Ahorros" in payload                                                   # el nombre sí
    assert "Vieja" not in payload and "Secreta" not in payload                    # ni archivadas ni de otros
    for secreto in (ahorros["id"], vieja["id"], "4242424", "7373737", "5151515", "user-a", "user-b", "@"):
        assert secreto not in payload, secreto                                    # ni ids, ni saldos, ni usuario, ni correo
    assert '"cuenta"' in payload and "usuario_id" not in payload and "cuenta_id" not in payload


def test_inv052_whatsapp_no_crea_transferencias(client, meta):
    tw._enlazar(client, meta)
    ef = _cuenta(client, "Efectivo", "efectivo", 100000)
    ah = _cuenta(client, "Ahorros", "ahorros_corriente", 0)
    # La IA no tiene herramienta de transferencias: solo registrar, deshacer y corregir
    nombres = {h["name"] for h in tw.wa.HERRAMIENTAS}
    assert nombres == {"registrar_movimientos", "deshacer_ultimo", "corregir_ultimo"}
    assert not any("transfer" in n for n in nombres) and "cuenta" not in tw.wa.HERRAMIENTAS[1]["input_schema"].get("properties", {})
    # Si el modelo (manipulado o equivocado) pide una herramienta inventada, no pasa nada
    meta["claude"].append(tw.herramienta("crear_transferencia", {"origen": "Efectivo", "destino": "Ahorros", "monto": 50000}))
    tw._msg(client, "pasa 50 mil de Efectivo a Ahorros")
    assert DemoTransferenciaDB._transferencias == {} and tw._tx(client) == []
    assert (_saldo(client, ef), _saldo(client, ah)) == (100000, 0)
    # Y si lo intenta como un «gasto» con otra cuenta: es un gasto normal, nunca un movimiento entre cuentas
    meta["claude"].append(tw.texto_claude("Las transferencias se hacen en la app."))
    tw._msg(client, "transfiere 50 mil de Efectivo a Ahorros")
    assert DemoTransferenciaDB._transferencias == {} and _texto_enviado(meta) == "Las transferencias se hacen en la app."
    assert "transferencia" in json.dumps(meta["payloads"][-1], ensure_ascii=False).lower()   # el prompt se lo recuerda


# ───────────── Asistente: cuentas_y_saldos de SOLO lectura (INV-023, INV-052) ─────────────

def test_inv052_asistente_cuentas_y_saldos_es_solo_lectura(client, monkeypatch):
    ef = _cuenta(client, "Efectivo", "efectivo", 100000)
    ah = _cuenta(client, "Ahorros", "ahorros_corriente", 5000)
    assert client.put(f"/api/v1/cuentas/{ah['id']}", json={"archivada": True}, headers=A).status_code == 200
    secreta = _cuenta(client, "Secreta", "efectivo", 9999, h=B)
    assert _tx(client, ef["id"], 30000).status_code == 200
    antes = (json.dumps(client.get("/api/v1/cuentas?incluir_archivadas=true", headers=A).json(), sort_keys=True),
             len(DemoTransaccionDB._transacciones), len(DemoTransferenciaDB._transferencias))

    def ejecutar(nombre, entrada, usuario="user-a"):
        return asyncio.run(asistente.ejecutar_herramienta(usuario, nombre, entrada))

    # El usuario sale del token: lo que pida el modelo (usuario_id, cuenta_id) se ignora
    salida, es_error = ejecutar("cuentas_y_saldos", {"usuario_id": "user-b", "cuenta_id": secreta["id"]})
    datos = json.loads(salida)
    assert not es_error and sorted(c["nombre"] for c in datos["cuentas"]) == ["Ahorros", "Efectivo"]
    assert {c["nombre"]: (c["saldo"], c["archivada"], c["tipo"]) for c in datos["cuentas"]} == {
        "Efectivo": (70000, False, "efectivo"), "Ahorros": (5000, True, "ahorros_corriente")}
    for prohibido in (ef["id"], ah["id"], secreta["id"], "user-a", "user-b", "Secreta", "usuario_id", '"id"'):
        assert prohibido not in salida, prohibido                                  # sin ids hacia Claude ni datos ajenos
    assert json.loads(ejecutar("cuentas_y_saldos", {}, "user-b")[0])["cuentas"][0]["saldo"] == 9999
    assert json.loads(ejecutar("cuentas_y_saldos", {}, "user-nuevo")[0]) == {"cuentas": []}

    # No existe ninguna herramienta que cree, cambie o borre: ni de cuentas ni de transferencias
    nombres = [h["name"] for h in asistente.HERRAMIENTAS]
    assert "cuentas_y_saldos" in nombres
    assert not any(p in n for n in nombres for p in ("crear", "editar", "borrar", "eliminar", "actualizar", "transfer", "archivar", "abonar"))
    for inventada in ("crear_cuenta", "archivar_cuenta", "crear_transferencia", "actualizar_cuenta"):
        assert ejecutar(inventada, {"nombre": "x"})[1] is True
    # Las escrituras del módulo de cuentas no se llaman nunca
    from app.models.cuentas import CuentaDB

    async def escritura(*_a, **_k):
        raise AssertionError("el asistente no debe escribir")

    for metodo in ("crear", "actualizar", "eliminar"):
        monkeypatch.setattr(CuentaDB, metodo, staticmethod(escritura))
    assert ejecutar("cuentas_y_saldos", {})[1] is False
    despues = (json.dumps(client.get("/api/v1/cuentas?incluir_archivadas=true", headers=A).json(), sort_keys=True),
               len(DemoTransaccionDB._transacciones), len(DemoTransferenciaDB._transferencias))
    assert despues == antes
    # Si las cuentas no responden, Claude recibe un error genérico (sin texto de la BD) y no se cae la pregunta
    from app.models.auth_estado import EstadoNoDisponible

    async def lenta(*_a, **_k):
        raise EstadoNoDisponible("plazo vencido secreto-de-la-bd")
    monkeypatch.setattr(CuentaDB, "listar", staticmethod(lenta))
    salida, es_error = ejecutar("cuentas_y_saldos", {})
    assert es_error and "secreto-de-la-bd" not in salida


# ───────────── Exportación: columna 8 «Cuenta» (CT-011 v1.1) ─────────────

URL_EXPORTAR = "/api/v1/exportaciones/transacciones"
ENCABEZADOS = ["Fecha", "Tipo", "Categoría", "Descripción", "Medio de pago", "Monto (COP)", "Origen", "Cuenta"]


def _csv(r):
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"), newline=""), delimiter=";"))


def _hoja(r):
    return [[c.value for c in fila] for fila in load_workbook(io.BytesIO(r.content))["Transacciones"].iter_rows()]


def test_inv052_exportar_incluye_columna_cuenta_al_final_y_no_incluye_transferencias(client):
    ef = _cuenta(client, "Efectivo", "efectivo", 100000)
    ah = _cuenta(client, "Ahorros", "ahorros_corriente", 0)
    secreta = _cuenta(client, "Secreta", "efectivo", 1000, h=B)
    assert _tx(client, ef["id"], 5000, fecha="2026-11-01", descripcion="con cuenta").status_code == 200
    assert _tx(client, None, 7000, fecha="2026-11-02", descripcion="sin cuenta").status_code == 200
    assert client.post("/api/v1/transferencias", json={"cuenta_origen_id": ef["id"], "cuenta_destino_id": ah["id"],
                                                       "monto": 40000, "fecha": "2026-11-03"}, headers=A).status_code == 200
    assert _tx(client, secreta["id"], 100, h=B, fecha="2026-11-01").status_code == 200
    # Una transacción de A con la cuenta de B (inyectada directo en la BD): sale vacía, nunca el nombre ajeno (INV-042)
    demo_ajena = _tx(client, None, 9000, fecha="2026-11-04", descripcion="ajena").json()
    DemoTransaccionDB._transacciones[demo_ajena["id"]]["cuenta_id"] = secreta["id"]

    r = client.get(URL_EXPORTAR, params={"desde": "2026-11", "formato": "csv"}, headers=A)
    assert r.status_code == 200, r.text
    filas = _csv(r)
    assert filas[0] == ENCABEZADOS and filas[0][-1] == "Cuenta"
    assert len(filas) == 4 and all(len(f) == 8 for f in filas)                    # 3 transacciones, ninguna transferencia
    assert [(f[3], f[7]) for f in filas[1:]] == [("con cuenta", "Efectivo"), ("sin cuenta", ""), ("ajena", "")]
    assert [f[:7] for f in filas[1:]][0] == ["2026-11-01", "Gasto", "Sin categoría", "con cuenta", "", "5000,00", "App"]   # 1 a 7 intactas
    assert "Secreta" not in r.content.decode("utf-8-sig") and "Transferencia" not in r.content.decode("utf-8-sig")
    x = client.get(URL_EXPORTAR, params={"desde": "2026-11", "formato": "xlsx"}, headers=A)
    hoja = _hoja(x)
    assert hoja[0] == ENCABEZADOS and [f[7] for f in hoja[1:]] in (["Efectivo", "", ""], ["Efectivo", None, None])
    assert len(hoja) == 4
    # El otro usuario ve solo lo suyo
    b = _csv(client.get(URL_EXPORTAR, params={"desde": "2026-11"}, headers=B))
    assert [(f[3], f[7]) for f in b[1:]] == [("x", "Secreta")]


def test_inv052_exportar_neutraliza_formulas_en_la_columna_cuenta(client):
    peligrosas = ['=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)"]
    for i, nombre in enumerate(peligrosas):
        c = _cuenta(client, nombre, "efectivo", 1000)
        assert _tx(client, c["id"], 10, fecha=f"2026-11-{i + 1:02d}").status_code == 200
    r = client.get(URL_EXPORTAR, params={"desde": "2026-11", "formato": "csv"}, headers=A)
    filas = _csv(r)[1:]
    assert len(filas) == 4
    for f, nombre in zip(filas, peligrosas):
        assert f[7] == "'" + nombre and not f[7].startswith(("=", "+", "-", "@"))   # apóstrofo delante: no es una fórmula
    assert all('"' in linea for linea in r.content.decode("utf-8-sig").split("\r\n")[1:5])
    libro = load_workbook(io.BytesIO(client.get(URL_EXPORTAR, params={"desde": "2026-11", "formato": "xlsx"}, headers=A).content))
    celdas = [fila[7] for fila in libro["Transacciones"].iter_rows(min_row=2)]
    assert [c.value for c in celdas] == peligrosas                                # el texto no cambia…
    assert all(c.data_type == "s" and c.quotePrefix for c in celdas)              # …pero es texto y con quotePrefix, nunca fórmula


def test_inv052_exportar_la_columna_cuenta_cuenta_para_los_topes(client, monkeypatch):
    """La columna 8 pesa en el tope de 4 MB (INV-044) y las cuentas no se leen si la sesión o los parámetros son inválidos."""
    from app.utils import exportar as generador
    fila = ("2026-11-01", "Gasto", "Sin categoría", "x", "", generador._monto(1), "App", "C" * 100)
    csv_bytes = generador._generar_csv(iter([[fila]]))
    assert csv_bytes.decode("utf-8-sig").splitlines()[1].endswith('"App";"' + "C" * 100 + '"')
    monkeypatch.setattr(generador, "MAX_BYTES", len(csv_bytes) - 1)
    with pytest.raises(generador.ExportacionDemasiadoGrande):
        generador._generar_csv(iter([[fila]]))
    llamadas = []

    async def listar(*a, **k):
        llamadas.append(a)
        return []
    from app.models.cuentas import CuentaDB
    monkeypatch.setattr(CuentaDB, "listar", staticmethod(listar))
    assert client.get(URL_EXPORTAR, params={"desde": "2026-11"}, headers={"Authorization": "Bearer malo"}).status_code == 401
    assert client.get(URL_EXPORTAR, params={"desde": "2026-13"}, headers=A).status_code == 422
    assert llamadas == []
