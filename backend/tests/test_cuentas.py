"""CHG-019 fase (a) · INV-046 a INV-051 · UC-016 · CT-012 y CT-003 v1.2: cuentas de dinero con saldo derivado.

El modo demo en memoria implementa las MISMAS reglas que los disparadores de `backend/sql/2026-11-25_cuentas.sql`; la
atomicidad y la concurrencia reales se prueban en PostgreSQL (`backend/sql/pruebas/08_comprobar_cuentas.sql`, `probar.sh`).
Las pruebas con `_ClienteFalso` comprueban la rama de Supabase (columnas reales, usuario de la sesión, traducción de errores).
"""
import asyncio
import threading
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.models import auth_estado, contadores, plataapp as modelos
from app.models.auth_estado import EstadoNoDisponible, MENSAJE_503
from app.models.cuentas import CuentaDB
from app.models.demo_db import DemoTransaccionDB
from conftest import auth_header

A = auth_header("user-a")
B = auth_header("user-b")
URL = "/api/v1/cuentas"
INEXISTENTE = "00000000-0000-4000-8000-000000000000"


def _cuenta(client, nombre="Efectivo", tipo="efectivo", saldo=100000, h=A, esperado=200):
    r = client.post(URL, json={"nombre": nombre, "tipo": tipo, "saldo_inicial": saldo}, headers=h)
    assert r.status_code == esperado, r.text
    return r.json()


def _tx(client, cuenta_id, monto=1000, tipo="gasto", fecha="2026-11-22", h=A, **extra):
    body = {"categoria_id": "", "monto": monto, "descripcion": "x", "fecha": fecha, "tipo": tipo, **extra}
    if cuenta_id is not None:
        body["cuenta_id"] = cuenta_id
    return client.post("/api/v1/transacciones", json=body, headers=h)


def _put_tx(client, tx, h=A, **cambios):
    body = {"categoria_id": "", "monto": tx["monto"], "descripcion": "x", "fecha": tx["fecha"], "tipo": tx["tipo"], **cambios}
    return client.put(f"/api/v1/transacciones/{tx['id']}", json=body, headers=h)


def _saldo(client, cuenta, h=A):
    r = client.get(f"{URL}/{cuenta['id']}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["saldo"]


def _cantidad_tx(client, h=A):
    return len(client.get("/api/v1/transacciones", headers=h).json())


# ───────────── INV-047: el saldo se deriva ─────────────

def test_inv047_saldo_es_inicial_mas_ingresos_menos_gastos(client):
    c = _cuenta(client, saldo=100000)
    assert _tx(client, c["id"], 50000, "ingreso").status_code == 200
    assert _tx(client, c["id"], 30000, "gasto").status_code == 200
    assert _saldo(client, c) == 120000


def test_inv047_las_transacciones_sin_cuenta_no_mueven_ningun_saldo(client):
    for monto, tipo in ((5000, "gasto"), (9000, "ingreso"), (1, "gasto")):
        assert _tx(client, None, monto, tipo).status_code == 200
    c = _cuenta(client, saldo=100000)
    assert _saldo(client, c) == 100000
    assert all(t["cuenta_id"] is None for t in client.get("/api/v1/transacciones", headers=A).json())


def test_inv047_editar_y_eliminar_transaccion_recalcula(client):
    ef = _cuenta(client, "Efectivo", saldo=100000)
    ah = _cuenta(client, "Ahorros", "ahorros_corriente", 50000)
    tx = _tx(client, ef["id"], 30000).json()
    assert _saldo(client, ef) == 70000
    tx = _put_tx(client, tx, monto=10000, cuenta_id=ef["id"]).json()
    assert _saldo(client, ef) == 90000
    tx = _put_tx(client, tx, cuenta_id=ah["id"]).json()
    assert (_saldo(client, ef), _saldo(client, ah)) == (100000, 40000)
    assert client.delete(f"/api/v1/transacciones/{tx['id']}", headers=A).status_code == 200
    assert (_saldo(client, ef), _saldo(client, ah)) == (100000, 50000)


def test_inv047_saldo_siempre_en_cop_sin_conversion(client, users):
    from app.models.user import UserDB
    usuario = asyncio.run(UserDB.create("usd@x.com", "Clave-123456", is_active=True, currency="USD"))
    assert usuario["currency"] == "USD"
    h = auth_header(usuario["id"])
    c = _cuenta(client, saldo=123456, h=h)
    lista = client.get(URL, headers=h).json()
    assert [(x["saldo_inicial"], x["saldo"]) for x in lista] == [(123456, 123456)] and c["saldo"] == 123456


def test_inv047_transacciones_de_fecha_futura_cuentan_en_el_saldo(client):
    c = _cuenta(client, saldo=50000)
    # CHG-027 (INV-063): 2099 ya no es una fecha admisible; se usa una futura DENTRO del rango (hoy + 200 días), misma intención
    futura = (contadores.hoy_colombia() + timedelta(days=200)).isoformat()
    assert _tx(client, c["id"], 10000, fecha=futura).status_code == 200
    assert _saldo(client, c) == 40000


# ───────────── Ciclo de vida y lista (INV-050) ─────────────

def test_cuenta_se_crea_edita_y_lista_con_saldo(client):
    c = _cuenta(client, "Efectivo", saldo=100000)
    assert c["tipo"] == "efectivo" and c["archivada"] is False and c["saldo"] == 100000
    r = client.put(f"{URL}/{c['id']}", json={"nombre": "Billetera"}, headers=A)
    assert r.status_code == 200 and r.json()["nombre"] == "Billetera"
    lista = client.get(URL, headers=A).json()
    assert [(x["nombre"], x["tipo"], x["saldo"]) for x in lista] == [("Billetera", "efectivo", 100000)]
    # el tipo NO se puede editar
    assert client.put(f"{URL}/{c['id']}", json={"tipo": "tarjeta_credito"}, headers=A).status_code == 422
    assert client.get(f"{URL}/{c['id']}", headers=A).json()["tipo"] == "efectivo"


def test_inv050_cuenta_con_transacciones_no_se_elimina_409(client):
    c = _cuenta(client)
    assert _tx(client, c["id"], 100).status_code == 200
    r = client.delete(f"{URL}/{c['id']}", headers=A)
    assert r.status_code == 409 and "Archívala en lugar de eliminarla" in r.json()["detail"]
    assert client.get(f"{URL}/{c['id']}", headers=A).status_code == 200


def test_inv050_cuenta_sin_transacciones_se_elimina(client):
    c = _cuenta(client)
    r = client.delete(f"{URL}/{c['id']}", headers=A)
    assert r.status_code == 200 and r.json() == {"message": "Cuenta eliminada"}
    assert client.get(URL, headers=A).json() == []
    assert client.get(f"{URL}/{c['id']}", headers=A).status_code == 404


def test_inv050_cuenta_archivada_esta_congelada(client):
    c = _cuenta(client, saldo=100000)
    tx = _tx(client, c["id"], 1000).json()
    assert client.put(f"{URL}/{c['id']}", json={"archivada": True}, headers=A).status_code == 200
    antes = _cantidad_tx(client)
    r = _tx(client, c["id"], 500)
    assert r.status_code == 409 and "está archivada" in r.json()["detail"] and _cantidad_tx(client) == antes
    r = _put_tx(client, tx, monto=2000, cuenta_id=c["id"])
    assert r.status_code == 409 and "está archivada" in r.json()["detail"]
    assert client.get(f"/api/v1/transacciones/{tx['id']}", headers=A).json()["monto"] == 1000
    r = client.delete(f"/api/v1/transacciones/{tx['id']}", headers=A)
    assert r.status_code == 409 and "está archivada" in r.json()["detail"]
    # también no se puede sacar una transacción hacia otra cuenta ni meter una a la archivada
    otra = _cuenta(client, "Otra", saldo=10)
    assert _put_tx(client, tx, cuenta_id=otra["id"]).status_code == 409
    # desarchivada, funciona
    assert client.put(f"{URL}/{c['id']}", json={"archivada": False}, headers=A).status_code == 200
    assert _tx(client, c["id"], 500).status_code == 200
    assert _put_tx(client, tx, monto=2000, cuenta_id=c["id"]).status_code == 200
    assert client.delete(f"/api/v1/transacciones/{tx['id']}", headers=A).status_code == 200


def test_inv050_archivar_y_desarchivar_con_saldo_distinto_de_cero(client):
    c = _cuenta(client, saldo=5000)
    assert client.put(f"{URL}/{c['id']}", json={"archivada": True}, headers=A).json()["archivada"] is True
    assert _saldo(client, c) == 5000
    assert client.get(URL, headers=A).json() == []
    assert client.get(f"{URL}?incluir_archivadas=true", headers=A).json()[0]["id"] == c["id"]
    assert client.get(f"{URL}?incluir_archivadas=false", headers=A).json() == []
    assert client.put(f"{URL}/{c['id']}", json={"archivada": False}, headers=A).json()["archivada"] is False
    assert [x["id"] for x in client.get(URL, headers=A).json()] == [c["id"]] and _saldo(client, c) == 5000


def test_inv050_tope_de_20_cuentas(client):
    ids = [_cuenta(client, f"Cuenta {n:02d}", saldo=0)["id"] for n in range(20)]
    client.put(f"{URL}/{ids[0]}", json={"archivada": True}, headers=A)   # las archivadas también cuentan
    r = client.post(URL, json={"nombre": "Una más", "tipo": "efectivo", "saldo_inicial": 0}, headers=A)
    assert r.status_code == 409 and "máximo de 20 cuentas" in r.json()["detail"]
    assert len(client.get(f"{URL}?incluir_archivadas=true", headers=A).json()) == 20
    _cuenta(client, "Una más", saldo=0, h=B)   # otro usuario no se ve afectado


def test_inv050_nombre_unico_por_usuario(client):
    c = _cuenta(client, "Efectivo")
    r = client.post(URL, json={"nombre": " efectivo ", "tipo": "efectivo", "saldo_inicial": 0}, headers=A)
    assert r.status_code == 409 and "Ya tienes una cuenta con ese nombre" in r.json()["detail"]
    otra = _cuenta(client, "Ahorros", "ahorros_corriente", 0)
    assert client.put(f"{URL}/{otra['id']}", json={"nombre": "EFECTIVO"}, headers=A).status_code == 409
    assert client.put(f"{URL}/{c['id']}", json={"nombre": "efectivo"}, headers=A).status_code == 200   # el suyo propio
    assert _cuenta(client, "Efectivo", h=B)["nombre"] == "Efectivo"   # otro usuario sí


# ───────────── INV-046: propiedad ─────────────

def test_inv046_cuenta_ajena_responde_404(client):
    ajena = _cuenta(client, h=B)
    inexistente = client.get(f"{URL}/{INEXISTENTE}", headers=A)
    assert inexistente.status_code == 404 and inexistente.json()["detail"] == "Cuenta no encontrada"
    for r in (client.get(f"{URL}/{ajena['id']}", headers=A),
              client.put(f"{URL}/{ajena['id']}", json={"nombre": "Mía"}, headers=A),
              client.delete(f"{URL}/{ajena['id']}", headers=A),
              client.get(f"{URL}/no-es-uuid", headers=A)):
        assert r.status_code == 404 and r.json() == inexistente.json()
    # nada cambió y A no ve la cuenta de B en su lista
    assert client.get(f"{URL}/{ajena['id']}", headers=B).json()["nombre"] == "Efectivo"
    assert client.get(URL, headers=A).json() == []


def test_inv046_transaccion_con_cuenta_ajena_404_crear_y_editar(client):
    ajena = _cuenta(client, h=B)
    r = _tx(client, ajena["id"], 100)
    assert r.status_code == 404 and r.json()["detail"] == "Cuenta no encontrada" and _cantidad_tx(client) == 0
    inexistente = _tx(client, INEXISTENTE, 100)
    assert inexistente.status_code == 404 and inexistente.json() == r.json()
    propia = _cuenta(client, "Mía")
    tx = _tx(client, propia["id"], 100).json()
    r = _put_tx(client, tx, cuenta_id=ajena["id"])
    assert r.status_code == 404 and r.json()["detail"] == "Cuenta no encontrada"
    assert client.get(f"/api/v1/transacciones/{tx['id']}", headers=A).json()["cuenta_id"] == propia["id"]
    assert _saldo(client, ajena, h=B) == 100000   # la cuenta ajena no se movió


def test_cuenta_id_con_formato_invalido_422(client):
    for malo in ("abc", "", "1" * 70, 5):
        assert _tx(client, malo, 100).status_code == 422


# ───────────── INV-048: saldo negativo ─────────────

def test_inv048_gasto_que_deja_saldo_negativo_se_rechaza_con_409(client):
    c = _cuenta(client, saldo=20000)
    r = _tx(client, c["id"], 30000)
    assert r.status_code == 409 and "Saldo insuficiente" in r.json()["detail"]
    assert _cantidad_tx(client) == 0 and _saldo(client, c) == 20000
    assert _tx(client, c["id"], 20000).status_code == 200 and _saldo(client, c) == 0   # justo hasta cero se permite


def test_inv048_tarjeta_de_credito_si_puede_quedar_negativa(client):
    t = _cuenta(client, "Visa", "tarjeta_credito", 0)
    assert _tx(client, t["id"], 30000).status_code == 200
    assert _saldo(client, t) == -30000


def test_inv048_eliminar_ingreso_que_dejaria_negativo_se_rechaza(client):
    c = _cuenta(client, saldo=0)
    ingreso = _tx(client, c["id"], 50000, "ingreso").json()
    assert _tx(client, c["id"], 40000).status_code == 200
    r = client.delete(f"/api/v1/transacciones/{ingreso['id']}", headers=A)
    assert r.status_code == 409 and "Saldo insuficiente" in r.json()["detail"]
    assert client.get(f"/api/v1/transacciones/{ingreso['id']}", headers=A).status_code == 200
    assert _saldo(client, c) == 10000


def test_inv048_editar_monto_o_cuenta_que_deja_negativo_se_rechaza(client):
    a = _cuenta(client, "A", saldo=0)
    b = _cuenta(client, "B", "ahorros_corriente", 0)
    ingreso = _tx(client, a["id"], 50000, "ingreso").json()
    gasto = _tx(client, a["id"], 20000).json()
    # subir el monto de un gasto por encima del saldo
    r = _put_tx(client, gasto, monto=80000, cuenta_id=a["id"])
    assert r.status_code == 409 and client.get(f"/api/v1/transacciones/{gasto['id']}", headers=A).json()["monto"] == 20000
    # bajar el monto de un ingreso ya gastado
    assert _put_tx(client, ingreso, monto=10000, cuenta_id=a["id"]).status_code == 409
    # pasar el ingreso a otra cuenta dejaría A en negativo
    r = _put_tx(client, ingreso, cuenta_id=b["id"])
    assert r.status_code == 409
    assert client.get(f"/api/v1/transacciones/{ingreso['id']}", headers=A).json()["cuenta_id"] == a["id"]
    assert (_saldo(client, a), _saldo(client, b)) == (30000, 0)
    # cambiar el tipo de ingreso a gasto también baja el saldo
    assert _put_tx(client, ingreso, tipo="gasto", cuenta_id=a["id"]).status_code == 409


def test_inv048_cambiar_saldo_inicial_que_deja_negativo_se_rechaza(client):
    c = _cuenta(client, saldo=100000)
    assert _tx(client, c["id"], 80000).status_code == 200
    r = client.put(f"{URL}/{c['id']}", json={"saldo_inicial": 50000}, headers=A)
    assert r.status_code == 409 and "Saldo insuficiente" in r.json()["detail"]
    assert _saldo(client, c) == 20000
    assert client.put(f"{URL}/{c['id']}", json={"saldo_inicial": 80000}, headers=A).json()["saldo"] == 0
    assert client.put(f"{URL}/{c['id']}", json={"saldo_inicial": 90000}, headers=A).json()["saldo"] == 10000


# ───────────── INV-051: montos ─────────────

def test_inv051_saldo_inicial_y_montos_respetan_tope_y_dos_decimales(client):
    for malo in (10000000000, 12.345, -1, 0.001):
        _cuenta(client, "Mala", "efectivo", malo, esperado=422)
    assert client.get(URL, headers=A).json() == []
    c = _cuenta(client, "Tope", saldo=9999999999.99)
    assert c["saldo_inicial"] == 9999999999.99
    # una transacción CON cuenta tiene el mismo tope y los mismos 2 decimales
    ok = _cuenta(client, "Con tx", saldo=0)
    for malo in (10000000000, 12.345, 0.001):
        r = _tx(client, ok["id"], malo, "ingreso")
        assert r.status_code == 422 and "no cumple el máximo permitido con cuenta de dinero" in r.json()["detail"]
    assert _tx(client, ok["id"], 9999999999.99, "ingreso").status_code == 200
    # sin cuenta rige INV-003, con el mismo tope y decimales (CHG-029)
    for malo in (10000000000, 20000000000.5, 12.345, 0.001):
        assert _tx(client, None, malo, "ingreso").status_code == 422, malo
    assert _tx(client, None, 9999999999.99, "ingreso").status_code == 200
    # tarjeta: la deuda inicial tampoco pasa del tope
    _cuenta(client, "Visa", "tarjeta_credito", -10000000000, esperado=422)


def test_inv051_los_montos_se_leen_con_decimal_y_rechazan_mas_de_dos_decimales(client):
    cabecera = {**A, "Content-Type": "application/json"}
    for n, crudo in enumerate(("0.001", "12.345", "1e-3")):
        r = client.post(URL, content=f'{{"nombre": "M{n}", "tipo": "efectivo", "saldo_inicial": {crudo}}}', headers=cabecera)
        assert r.status_code == 422, crudo
    for n, (crudo, esperado) in enumerate((("0.10", 0.1), ("100.5", 100.5))):
        r = client.post(URL, content=f'{{"nombre": "Ok{n}", "tipo": "efectivo", "saldo_inicial": {crudo}}}', headers=cabecera)
        assert r.status_code == 200 and r.json()["saldo_inicial"] == esperado and r.json()["saldo"] == esperado
    c = _cuenta(client, "Cent", saldo=0)
    assert _tx(client, c["id"], 0.1, "ingreso").status_code == 200
    assert _tx(client, c["id"], 0.2, "ingreso").status_code == 200
    assert _saldo(client, c) == 0.3   # sin error de redondeo de float (0.1 + 0.2 = 0.30000000000000004)


def test_inv051_put_solo_con_cuenta_id_valida_el_monto_guardado(client):
    c = _cuenta(client, saldo=0)
    # datos anteriores a CHG-019 (sin cuenta) con un monto que no cumple el tope ni los 2 decimales
    decimales = asyncio.run(DemoTransaccionDB.crear("user-a", "", 12.345, "x", "2026-11-22", "ingreso"))
    enorme = asyncio.run(DemoTransaccionDB.crear("user-a", "", 20000000000, "x", "2026-11-22", "ingreso"))
    valida = asyncio.run(DemoTransaccionDB.crear("user-a", "", 500, "x", "2026-11-22", "ingreso"))
    for vieja in (decimales, enorme):
        r = _put_tx(client, vieja, cuenta_id=c["id"])
        assert r.status_code == 422
        assert r.json()["detail"] == "El monto de esta transacción no cumple el máximo permitido con cuenta de dinero"
        guardada = client.get(f"/api/v1/transacciones/{vieja['id']}", headers=A).json()
        assert guardada["cuenta_id"] is None and guardada["monto"] == vieja["monto"]
    assert _saldo(client, c) == 0
    r = _put_tx(client, valida, cuenta_id=c["id"])
    assert r.status_code == 200 and r.json()["cuenta_id"] == c["id"] and _saldo(client, c) == 500


def test_inv051_saldo_inicial_negativo_solo_en_tarjeta_de_credito(client):
    t = _cuenta(client, "Visa", "tarjeta_credito", -250000)
    assert t["saldo"] == -250000 and _saldo(client, t) == -250000
    e = _cuenta(client, "Efectivo", saldo=10)
    r = client.put(f"{URL}/{e['id']}", json={"saldo_inicial": -5}, headers=A)
    assert r.status_code == 422 and _saldo(client, e) == 10
    assert client.put(f"{URL}/{t['id']}", json={"saldo_inicial": -300000}, headers=A).json()["saldo"] == -300000


def test_inv051_tipo_invalido_422(client):
    r = client.post(URL, json={"nombre": "X", "tipo": "cripto", "saldo_inicial": 0}, headers=A)
    assert r.status_code == 422
    assert client.post(URL, json={"nombre": "", "tipo": "efectivo"}, headers=A).status_code == 422
    assert client.post(URL, json={"nombre": "x" * 101, "tipo": "efectivo"}, headers=A).status_code == 422
    assert client.post(URL, json={"nombre": "   ", "tipo": "efectivo"}, headers=A).status_code == 422
    assert client.get(URL, headers=A).json() == []


# ───────────── Coexistencia con el medio de pago y PUT ─────────────

def test_medio_de_pago_y_cuenta_coexisten(client):
    c = _cuenta(client, "Ahorros", "ahorros_corriente", 100000)
    tx = _tx(client, c["id"], 1000, medio_pago="debito").json()
    assert (tx["medio_pago"], tx["cuenta_id"]) == ("debito", c["id"])
    sin_cuenta = _put_tx(client, tx, cuenta_id=None, medio_pago="debito").json()
    assert (sin_cuenta["medio_pago"], sin_cuenta["cuenta_id"]) == ("debito", None) and _saldo(client, c) == 100000
    con_cuenta = _put_tx(client, tx, cuenta_id=c["id"], medio_pago=None).json()
    assert (con_cuenta["medio_pago"], con_cuenta["cuenta_id"]) == (None, c["id"])


def test_put_conserva_quita_o_reemplaza_cuenta_como_medio_pago(client):
    a = _cuenta(client, "A", saldo=100000)
    b = _cuenta(client, "B", "ahorros_corriente", 100000)
    tx = _tx(client, a["id"], 1000, medio_pago="efectivo").json()
    conserva = _put_tx(client, tx, monto=2000).json()   # sin enviar cuenta_id
    assert conserva["cuenta_id"] == a["id"] and conserva["monto"] == 2000 and _saldo(client, a) == 98000
    quita = _put_tx(client, tx, cuenta_id=None).json()
    assert quita["cuenta_id"] is None and _saldo(client, a) == 100000
    reemplaza = _put_tx(client, tx, cuenta_id=a["id"]).json()
    assert reemplaza["cuenta_id"] == a["id"]
    cambia = _put_tx(client, tx, cuenta_id=b["id"]).json()
    assert cambia["cuenta_id"] == b["id"] and (_saldo(client, a), _saldo(client, b)) == (100000, 99000)


# ───────────── Seguridad de las respuestas y límites ─────────────

def test_las_respuestas_no_traen_datos_de_la_cuenta_de_usuario_ni_ajenos(client, users):
    from app.models.user import UserDB
    yo = asyncio.run(UserDB.create("yo@x.com", "Clave-123456", full_name="Yo", is_active=True))
    otro = asyncio.run(UserDB.create("otro@x.com", "Clave-123456", full_name="Otro", is_active=True))
    _cuenta(client, "Mía", h=auth_header(yo["id"]))
    _cuenta(client, "Suya", h=auth_header(otro["id"]))
    respuestas = [client.get(URL, headers=auth_header(yo["id"])),
                  client.get(f"{URL}?incluir_archivadas=true", headers=auth_header(yo["id"]))]
    for r in respuestas:
        assert "hashed_password" not in r.text and "otro@x.com" not in r.text and "Suya" not in r.text
        assert [set(x) for x in r.json()] == [{"id", "usuario_id", "nombre", "tipo", "saldo_inicial", "saldo", "archivada", "created_at"}]
        assert all(x["usuario_id"] == yo["id"] for x in r.json())


def test_sin_sesion_responde_401(client):
    for r in (client.get(URL), client.post(URL, json={"nombre": "x", "tipo": "efectivo"}),
              client.get(URL, headers={"Authorization": "Bearer basura"})):
        assert r.status_code in (401, 422)
    assert client.get(URL, headers={"Authorization": "Bearer basura"}).status_code == 401


def test_las_altas_tienen_limite_por_minuto(client):
    from app.api.routes.cuentas import LIMITE_ALTAS_POR_MINUTO
    codigos = [client.post(URL, json={"nombre": f"C{n}", "tipo": "efectivo", "saldo_inicial": 0}, headers=A).status_code
               for n in range(LIMITE_ALTAS_POR_MINUTO + 1)]
    assert codigos[20:LIMITE_ALTAS_POR_MINUTO] == [409] * (LIMITE_ALTAS_POR_MINUTO - 20)   # el tope de 20 llega antes
    assert codigos[-1] == 429
    assert client.post(URL, json={"nombre": "Libre", "tipo": "efectivo"}, headers=B).status_code == 200   # por usuario


# ───────────── Rama de Supabase con cliente FALSO ─────────────

# Esquema real (backend/sql/2026-11-25_cuentas.sql y PLATAAPP_SCHEMA.sql): `transacciones` no tiene `created_at`
COLUMNAS_REALES = {
    "cuentas": {"id", "usuario_id", "nombre", "tipo", "saldo_inicial", "archivada", "created_at"},
    "transacciones": {"id", "usuario_id", "categoria_id", "monto", "descripcion", "fecha", "tipo", "medio_pago", "cuenta_id"},
}
FILA_CUENTA = {"id": INEXISTENTE, "usuario_id": "user-a", "nombre": "Efectivo", "tipo": "efectivo",
               "saldo_inicial": 1000, "archivada": False, "created_at": "2026-11-25T10:00:00+00:00"}


class _ErrorPG(Exception):
    """Como el APIError de postgrest: SQLSTATE en `code` y un texto de la BD que NUNCA debe llegar a la persona."""

    def __init__(self, code, message="secreto-de-la-bd id=7a3f detail=host-interno"):
        super().__init__(message)
        self.code, self.message = code, message


class _Consulta:
    def __init__(self, cliente, tabla, args=None):
        self.cliente, self.tabla, self.args, self.llamadas = cliente, tabla, args, []

    def __getattr__(self, nombre):
        def registrar(*args, **kwargs):
            self.llamadas.append((nombre, args))
            return self
        return registrar

    def execute(self):
        self.cliente.consultas.append(self)
        return SimpleNamespace(data=self.cliente.fuente(self))

    def valor(self, nombre):
        return [a for n, a in self.llamadas if n == nombre]


class _ClienteFalso:
    def __init__(self, fuente):
        self.fuente, self.consultas = fuente, []

    def table(self, nombre):
        return _Consulta(self, nombre)

    def rpc(self, nombre, args):
        return _Consulta(self, "rpc:" + nombre, args)


def _con_supabase_falso(monkeypatch, fuente):
    cliente = _ClienteFalso(fuente)
    monkeypatch.setattr(auth_estado, "_modo", lambda: "bd")          # cuentas: cliente dedicado con plazo
    monkeypatch.setattr(auth_estado, "_cliente_estado", cliente)
    monkeypatch.setattr(modelos, "_supabase_ok", lambda: True)       # transacciones: ahora también el cliente dedicado (CHG-026); get_client queda por las demás tablas
    monkeypatch.setattr(modelos.SupabaseDB, "get_client", staticmethod(lambda: cliente))
    return cliente


def _fuente_basica(q):
    if q.tabla == "cuentas" and q.valor("select"):
        return [FILA_CUENTA]
    return []


def test_req_n022_listar_cuentas_hace_pocas_consultas(client, monkeypatch):
    filas = [{**FILA_CUENTA, "id": f"00000000-0000-4000-8000-{n:012d}", "nombre": f"C{n}", "saldo": 1000 + n} for n in range(20)]
    cliente = _con_supabase_falso(monkeypatch, lambda q: filas if q.tabla == "rpc:cuentas_con_saldo" else [])
    r = client.get(URL, headers=A)
    assert r.status_code == 200 and len(r.json()) == 20 and r.json()[3]["saldo"] == 1003
    assert [q.tabla for q in cliente.consultas] == ["rpc:cuentas_con_saldo"]          # UNA consulta agregada, sin N+1
    assert cliente.consultas[0].args == {"p_usuario_id": "user-a"}                    # el usuario sale de la sesión
    cliente.consultas.clear()
    client.get(URL, headers=B)
    assert cliente.consultas[0].args == {"p_usuario_id": "user-b"}


def test_inv046_supabase_usa_solo_columnas_reales_y_filtra_por_el_usuario_de_la_sesion(client, monkeypatch):
    def fuente(q):
        if q.tabla == "cuentas" and q.valor("select"):
            return [FILA_CUENTA]
        if q.tabla == "cuentas" and (q.valor("insert") or q.valor("update")):
            return [{**FILA_CUENTA, **(q.valor("insert") or q.valor("update"))[0][0]}]
        if q.tabla == "rpc:cuentas_con_saldo":
            return [{**FILA_CUENTA, "saldo": 1000}]
        if q.tabla == "cuentas" and q.valor("delete"):
            return [FILA_CUENTA]
        if q.tabla == "transacciones" and q.valor("insert"):
            return [q.valor("insert")[0][0]]
        if q.tabla == "transacciones":
            return [{"id": INEXISTENTE, "usuario_id": "user-a", "categoria_id": None, "monto": 5, "descripcion": "",
                     "fecha": "2026-11-22", "tipo": "gasto", "medio_pago": None, "cuenta_id": INEXISTENTE}]
        return []
    cliente = _con_supabase_falso(monkeypatch, fuente)
    assert client.post(URL, json={"nombre": " Nueva  cuenta ", "tipo": "efectivo", "saldo_inicial": "12.50"}, headers=A).status_code == 200
    assert client.put(f"{URL}/{INEXISTENTE}", json={"nombre": "Otro", "saldo_inicial": 5, "archivada": True}, headers=A).status_code == 200
    assert _tx(client, INEXISTENTE, 100, medio_pago="debito").status_code == 200
    assert client.put(f"/api/v1/transacciones/{INEXISTENTE}", json={
        "monto": 5, "fecha": "2026-11-22", "tipo": "gasto", "cuenta_id": INEXISTENTE}, headers=A).status_code == 200
    assert client.delete(f"{URL}/{INEXISTENTE}", headers=A).status_code == 200
    vistos = {"cuentas": set(), "transacciones": set()}
    for q in cliente.consultas:
        if q.tabla not in vistos:
            continue
        for args in q.valor("select"):
            vistos[q.tabla] |= {c for c in args[0].split(",") if c != "*"}
        for nombre in ("insert", "update"):
            for (fila,) in q.valor(nombre):
                vistos[q.tabla] |= set(fila)
        for args in q.valor("eq"):
            vistos[q.tabla].add(args[0])
        if q.valor("eq"):   # toda consulta por id o lista filtra por el usuario de la sesión, nunca por uno ajeno
            assert ("usuario_id", "user-a") in q.valor("eq")
    assert vistos["cuentas"] and vistos["cuentas"] <= COLUMNAS_REALES["cuentas"], vistos["cuentas"] - COLUMNAS_REALES["cuentas"]
    assert vistos["transacciones"] <= COLUMNAS_REALES["transacciones"]
    creada = next(q for q in cliente.consultas if q.tabla == "cuentas" and q.valor("insert")).valor("insert")[0][0]
    assert creada["usuario_id"] == "user-a" and creada["nombre"] == "Nueva cuenta" and creada["saldo_inicial"] == "12.50"
    assert "saldo" not in creada and "archivada" not in creada                 # el saldo jamás se guarda (INV-047)
    tx = next(q for q in cliente.consultas if q.tabla == "transacciones" and q.valor("insert")).valor("insert")[0][0]
    assert tx["cuenta_id"] == INEXISTENTE and tx["usuario_id"] == "user-a"


@pytest.mark.parametrize("codigo, estado, texto", [
    ("FZ001", 409, "Saldo insuficiente"), ("FZ002", 409, "está archivada"), ("23503", 404, "Cuenta no encontrada")])
def test_inv048_el_rechazo_no_guarda_nada_y_traduce_el_error_de_la_bd(client, monkeypatch, capsys, codigo, estado, texto):
    def fuente(q):
        if q.tabla == "cuentas":
            return [FILA_CUENTA]
        if q.tabla == "transacciones" and q.valor("insert"):
            raise _ErrorPG(codigo)
        return []
    _con_supabase_falso(monkeypatch, fuente)
    r = _tx(client, INEXISTENTE, 30000)
    assert r.status_code == estado and texto in r.json()["detail"]
    assert "secreto" not in r.text and "7a3f" not in r.text and "host-interno" not in r.text
    assert "secreto" not in capsys.readouterr().out                      # tampoco en los registros


def test_inv048_la_edicion_y_la_baja_tambien_traducen_el_error_de_la_bd(client, monkeypatch):
    fila_tx = {"id": INEXISTENTE, "usuario_id": "user-a", "categoria_id": None, "monto": 5, "descripcion": "",
               "fecha": "2026-11-22", "tipo": "gasto", "medio_pago": None, "cuenta_id": INEXISTENTE}
    estado = {"error": "FZ001"}

    def fuente(q):
        if q.tabla == "cuentas":
            return [FILA_CUENTA]
        if q.tabla == "transacciones" and (q.valor("update") or q.valor("delete")):
            raise _ErrorPG(estado["error"])
        return [fila_tx] if q.tabla == "transacciones" else []
    _con_supabase_falso(monkeypatch, fuente)
    cuerpo = {"monto": 9, "fecha": "2026-11-22", "tipo": "gasto", "cuenta_id": INEXISTENTE}
    for codigo, texto in (("FZ001", "Saldo insuficiente"), ("FZ002", "está archivada")):
        estado["error"] = codigo
        for r in (client.put(f"/api/v1/transacciones/{INEXISTENTE}", json=cuerpo, headers=A),
                  client.delete(f"/api/v1/transacciones/{INEXISTENTE}", headers=A)):
            assert r.status_code == 409 and texto in r.json()["detail"] and "secreto" not in r.text


@pytest.mark.parametrize("metodo, codigo, estado, texto", [
    ("post", "23505", 409, "Ya tienes una cuenta con ese nombre"),
    ("post", "FZ003", 409, "máximo de 20 cuentas"),
    ("put", "23505", 409, "Ya tienes una cuenta con ese nombre"),
    ("put", "FZ001", 409, "Saldo insuficiente"),
    ("delete", "23503", 409, "Archívala en lugar de eliminarla")])
def test_los_errores_de_la_bd_en_cuentas_son_409_sin_detalles(client, monkeypatch, metodo, codigo, estado, texto):
    def fuente(q):
        if q.tabla == "cuentas" and q.valor("select"):
            return [FILA_CUENTA]
        if q.tabla == "cuentas":
            raise _ErrorPG(codigo)
        return []
    _con_supabase_falso(monkeypatch, fuente)
    if metodo == "post":
        r = client.post(URL, json={"nombre": "X", "tipo": "efectivo", "saldo_inicial": 0}, headers=A)
    elif metodo == "put":
        r = client.put(f"{URL}/{INEXISTENTE}", json={"nombre": "Y", "saldo_inicial": 1}, headers=A)
    else:
        r = client.delete(f"{URL}/{INEXISTENTE}", headers=A)
    assert r.status_code == estado and texto in r.json()["detail"]
    assert "secreto" not in r.text and "7a3f" not in r.text


def test_fallos_de_la_bd_en_cuentas_son_503_fail_closed_sin_detalles(client, monkeypatch, capsys):
    def roto(q):
        raise RuntimeError("secreto host-interno 10.0.0.7 password=abc")
    _con_supabase_falso(monkeypatch, roto)
    for r in (client.get(URL, headers=A), client.get(f"{URL}/{INEXISTENTE}", headers=A),
              client.post(URL, json={"nombre": "X", "tipo": "efectivo"}, headers=A),
              client.put(f"{URL}/{INEXISTENTE}", json={"nombre": "Y"}, headers=A),
              client.delete(f"{URL}/{INEXISTENTE}", headers=A)):
        assert r.status_code == 503 and r.json() == {"detail": MENSAJE_503}
        assert "secreto" not in r.text
    assert "secreto" not in capsys.readouterr().out
    # una respuesta inesperada también es 503 (nunca se «deja pasar»)
    _con_supabase_falso(monkeypatch, lambda q: {"no": "es una lista"})
    assert client.get(URL, headers=A).status_code == 503
    _con_supabase_falso(monkeypatch, lambda q: [{"id": "x"}])
    assert client.get(URL, headers=A).status_code == 503


def test_la_lista_nunca_devuelve_cuentas_de_otro_usuario_aunque_la_bd_las_envie(client, monkeypatch):
    ajena = {**FILA_CUENTA, "usuario_id": "user-b", "saldo": 1}
    _con_supabase_falso(monkeypatch, lambda q: [ajena] if q.tabla == "rpc:cuentas_con_saldo" else [])
    assert client.get(URL, headers=A).status_code == 503


def test_en_produccion_sin_supabase_las_cuentas_no_usan_la_memoria(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    for operacion in (lambda: CuentaDB.listar("user-a"), lambda: CuentaDB.obtener_por_id(INEXISTENTE, "user-a")):
        with pytest.raises(EstadoNoDisponible):
            asyncio.run(operacion())


# ───────────── I-1: ejecutor PROPIO y acotado de cuentas (ADR-009, BL-043) ─────────────

def _huecos_cuentas():
    from app.models import cuentas as cuentas_mod
    return cuentas_mod._huecos._value


def _esperar_huecos_cuentas(n, plazo=3.0):
    fin = time.monotonic() + plazo
    while _huecos_cuentas() != n and time.monotonic() < fin:
        time.sleep(0.01)
    return _huecos_cuentas()


def _fuente_lenta(espera, hilos, falla=None):
    def fuente(q):
        hilos.append(threading.current_thread().name)
        time.sleep(espera)
        if falla:
            raise falla
        return [FILA_CUENTA] if q.tabla == "rpc:cuentas_con_saldo" else []
    return fuente


def test_i1_cuentas_usa_su_propio_ejecutor_de_4_hilos_y_no_los_de_auth_estado(client, monkeypatch):
    from app.models import cuentas as cuentas_mod
    hilos = []
    _con_supabase_falso(monkeypatch, _fuente_lenta(0, hilos))
    assert cuentas_mod.MAX_HILOS_CUENTAS == 4 and cuentas_mod._ejecutor is not auth_estado._ejecutor
    assert client.get(URL, headers=A).status_code == 200
    assert hilos and all(h.startswith("cuentas") and "auth-estado" not in h for h in hilos)


def test_i1_sin_hueco_503_inmediato_sin_encolar_ni_llamar_a_la_bd(client, monkeypatch):
    from app.models import cuentas as cuentas_mod
    hilos = []
    _con_supabase_falso(monkeypatch, _fuente_lenta(0, hilos))
    tomados = 0
    while cuentas_mod._huecos.acquire(blocking=False):
        tomados += 1
    try:
        inicio = time.monotonic()
        r = client.get(URL, headers=A)
        assert r.status_code == 503 and r.json() == {"detail": MENSAJE_503}
        assert time.monotonic() - inicio < 0.5 and hilos == []
    finally:
        for _ in range(tomados):
            cuentas_mod._huecos.release()


def test_i1_el_hueco_se_libera_tras_terminar_tras_excepcion_y_tras_cancelacion(monkeypatch):
    base = _huecos_cuentas()
    hilos = []
    _con_supabase_falso(monkeypatch, _fuente_lenta(0, hilos))
    assert len(asyncio.run(CuentaDB.listar("user-a"))) == 1
    assert _esperar_huecos_cuentas(base) == base                       # tras terminar
    _con_supabase_falso(monkeypatch, _fuente_lenta(0, hilos, RuntimeError("secreto")))
    with pytest.raises(EstadoNoDisponible):
        asyncio.run(CuentaDB.listar("user-a"))
    assert _esperar_huecos_cuentas(base) == base                       # tras excepción
    _con_supabase_falso(monkeypatch, _fuente_lenta(0.5, hilos))

    async def cancelar():
        tarea = asyncio.create_task(CuentaDB.listar("user-a"))
        await asyncio.sleep(0.1)
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea
    asyncio.run(cancelar())
    assert _esperar_huecos_cuentas(base) == base                       # tras cancelación (al terminar el hilo)


def test_i1_con_la_bd_lenta_las_cuentas_no_dan_503_a_los_logins_de_otras_personas(client, users, monkeypatch):
    """No interferencia: con las 4 llamadas de cuentas en vuelo (y varias más rechazadas), los 8 hilos de auth-estado siguen
    libres y el login de OTRA persona responde 200."""
    from app.models import cuentas as cuentas_mod
    from app.models.user import UserDB
    hilos = []
    _con_supabase_falso(monkeypatch, _fuente_lenta(0.8, hilos))
    monkeypatch.setattr(auth_estado, "_modo", lambda: "memoria")   # el login usa su almacén; cuentas usa el cliente falso
    monkeypatch.setattr(cuentas_mod, "_modo", lambda: "bd")
    asyncio.run(UserDB.create("otra@x.com", "Clave-123456", is_active=True))

    async def tormenta():
        return await asyncio.gather(*[CuentaDB.listar("user-a") for _ in range(12)], return_exceptions=True)
    resultado = []
    hilo = threading.Thread(target=lambda: resultado.extend(asyncio.run(tormenta())))
    hilo.start()
    time.sleep(0.2)
    r = client.post("/api/v1/auth/login", json={"email": "otra@x.com", "password": "Clave-123456"})
    assert r.status_code == 200 and r.json()["access_token"]
    assert asyncio.run(auth_estado.ejecutar("sonda", lambda: "ok")) == "ok"   # los 8 hilos de auth-estado, libres
    hilo.join()
    assert sum(isinstance(x, EstadoNoDisponible) for x in resultado) == 8     # 4 corren, 8 sin hueco = 503
    assert len(hilos) == 4 and all(h.startswith("cuentas") for h in hilos)
    _esperar_huecos_cuentas(cuentas_mod.MAX_HILOS_CUENTAS)


# ───────────── M-1 / FZ004: traducción de errores de la BD ─────────────

def test_m1_monto_que_desborda_numeric_12_2_en_transaccion_sin_cuenta_es_422_no_503(client, monkeypatch, capsys):
    """Defensa en profundidad: INV-003 ya rechaza el exceso (CHG-029); si aun así la BD lanza 22003, es 422 y no 503."""
    def fuente(q):
        if q.tabla == "transacciones" and (q.valor("insert") or q.valor("update")):
            raise _ErrorPG("22003")
        return [{"id": INEXISTENTE, "usuario_id": "user-a", "categoria_id": None, "monto": 5, "descripcion": "",
                 "fecha": "2026-11-22", "tipo": "gasto", "medio_pago": None, "cuenta_id": None}]
    _con_supabase_falso(monkeypatch, fuente)
    r = _tx(client, None, 5000)
    assert r.status_code == 422 and r.json() == {"detail": "El monto es demasiado grande"}
    r = client.put(f"/api/v1/transacciones/{INEXISTENTE}", headers=A, json={
        "monto": 5000, "fecha": "2026-11-22", "tipo": "gasto", "descripcion": ""})
    assert r.status_code == 422 and "demasiado grande" in r.json()["detail"]
    assert "secreto" not in r.text and "secreto" not in capsys.readouterr().out


def test_fz004_cambiar_el_tipo_de_una_cuenta_en_la_bd_se_traduce_a_422_sin_detalles(client, monkeypatch):
    def fuente(q):
        if q.tabla == "cuentas" and q.valor("update"):
            raise _ErrorPG("FZ004")
        return [FILA_CUENTA] if q.tabla in ("cuentas", "rpc:cuentas_con_saldo") else []
    _con_supabase_falso(monkeypatch, fuente)
    r = client.put(f"{URL}/{INEXISTENTE}", json={"nombre": "Y"}, headers=A)
    assert r.status_code == 422 and "tipo" in r.json()["detail"] and "secreto" not in r.text and "FZ004" not in r.text


def test_inv051_el_saldo_sale_redondeado_a_2_decimales(client, monkeypatch):
    fila = {**FILA_CUENTA, "saldo": 1234.5600000001, "saldo_inicial": "10.10"}
    _con_supabase_falso(monkeypatch, lambda q: [fila] if q.tabla == "rpc:cuentas_con_saldo" else [])
    c = client.get(URL, headers=A).json()[0]
    assert c["saldo"] == 1234.56 and c["saldo_inicial"] == 10.1
