"""CHG-024 (CHG-019 fase b) · INV-046, INV-047, INV-049, INV-051 · UC-016 · CT-012 §Transferencias.

El modo demo en memoria implementa las MISMAS reglas que el disparador `fz001_saldo_transferencias` de la migración; la
atomicidad y la concurrencia reales se prueban en PostgreSQL (`backend/sql/pruebas/09_comprobar_transferencias.sql`, `probar.sh`).
Las pruebas con cliente falso de Supabase comprueban la rama real (columnas, usuario de la sesión, traducción de errores, 503).
"""
import asyncio
import json
import time

import pytest

from app.models.auth_estado import MENSAJE_503
from test_cuentas import (A, B, INEXISTENTE, _ErrorPG, _cuenta, _con_supabase_falso, _saldo, _tx, FILA_CUENTA)

URL = "/api/v1/transferencias"
CUENTAS = "/api/v1/cuentas"
COLUMNAS_REALES = {"id", "usuario_id", "cuenta_origen_id", "cuenta_destino_id", "monto", "fecha", "descripcion", "created_at"}
FILA_TRANSFERENCIA = {"id": INEXISTENTE, "usuario_id": "user-a", "cuenta_origen_id": INEXISTENTE,
                      "cuenta_destino_id": "11111111-1111-4111-8111-111111111111", "monto": 100, "fecha": "2026-11-10",
                      "descripcion": None, "created_at": "2026-11-25T10:00:00+00:00"}
DESTINO = "11111111-1111-4111-8111-111111111111"


def _transferir(client, origen, destino, monto=40000, fecha="2026-11-10", h=A, **extra):
    cuerpo = {"cuenta_origen_id": origen["id"] if isinstance(origen, dict) else origen,
              "cuenta_destino_id": destino["id"] if isinstance(destino, dict) else destino,
              "monto": monto, "fecha": fecha, **extra}
    return client.post(URL, json=cuerpo, headers=h)


def _par(client, saldo_origen=100000, saldo_destino=0, h=A):
    return (_cuenta(client, "Efectivo", "efectivo", saldo_origen, h=h),
            _cuenta(client, "Ahorros", "ahorros_corriente", saldo_destino, h=h))


# ───────────── INV-049: la transferencia mueve los dos saldos juntos ─────────────

def test_inv049_transferencia_mueve_ambos_saldos_juntos(client):
    ef, ah = _par(client)
    r = _transferir(client, ef, ah, 40000, descripcion="Ahorro del mes")
    assert r.status_code == 200, r.text
    t = r.json()
    assert set(t) == COLUMNAS_REALES and t["usuario_id"] == "user-a" and t["monto"] == 40000
    assert (t["cuenta_origen_id"], t["cuenta_destino_id"], t["fecha"], t["descripcion"]) == (ef["id"], ah["id"], "2026-11-10", "Ahorro del mes")
    assert (_saldo(client, ef), _saldo(client, ah)) == (60000, 40000)


def test_inv049_no_cuenta_como_ingreso_ni_gasto_en_resumen_presupuestos_reportes_asistente(client):
    from app.utils.asistente import ejecutar_herramienta
    ef, ah = _par(client)
    assert _tx(client, ef["id"], 1000, "gasto", fecha="2026-11-05").status_code == 200

    def foto():
        exp = client.get("/api/v1/exportaciones/transacciones", params={"desde": "2026-11", "hasta": "2026-11", "formato": "csv"}, headers=A)
        herramientas = [asyncio.run(ejecutar_herramienta("user-a", n, {"mes": "2026-11"}))
                        for n in ("resumen_mes", "movimientos_principales", "totales_por_categoria", "totales_por_medio_pago")]
        return (client.get("/api/v1/transacciones/resumen/2026-11", headers=A).json(),
                client.get("/api/v1/transacciones", headers=A).json(),
                client.get("/api/v1/transacciones?mes=2026-11", headers=A).json(),
                client.get("/api/v1/presupuestos/2026-11", headers=A).json(),
                exp.status_code, exp.content, herramientas)
    antes = foto()
    assert _transferir(client, ef, ah, 40000).status_code == 200
    despues = foto()
    assert despues == antes                                                     # nada cambia en ninguna superficie
    assert antes[0] == {"ingresos": 0.0, "gastos": 1000.0, "balance": -1000.0, "total_transacciones": 1}
    assert len(despues[1]) == 1 and json.loads(despues[6][0][0])["gastos"] == 1000   # solo el gasto; la transferencia no está
    assert (_saldo(client, ef), _saldo(client, ah)) == (59000, 40000)


def test_inv049_aparece_en_la_lista_de_movimientos(client):
    ef, ah = _par(client)
    for fecha in ("2026-11-02", "2026-11-20", "2026-10-30"):
        assert _transferir(client, ef, ah, 100, fecha=fecha).status_code == 200
    assert _transferir(client, ef, ah, 100, fecha="2026-11-20").status_code == 200
    lista = client.get(f"{URL}?mes=2026-11", headers=A).json()
    assert [t["fecha"] for t in lista] == ["2026-11-20", "2026-11-20", "2026-11-02"]   # recientes primero
    assert lista[0]["id"] > lista[1]["id"]                                             # y, a igual fecha, id desc
    assert all(t["cuenta_origen_id"] == ef["id"] and t["cuenta_destino_id"] == ah["id"] and t["monto"] == 100 for t in lista)
    assert len(client.get(URL, headers=A).json()) == 4                                 # sin mes: todas
    assert client.get(URL, headers=B).json() == []                                     # cada quien, las suyas
    for malo in ("2026-13", "26-11", "2026-1", "abc", "2026-11-01"):
        r = client.get(URL, params={"mes": malo}, headers=A)
        assert r.status_code == 422 and r.json() == {"detail": "Formato de mes inválido (YYYY-MM)"}


def test_inv049_origen_y_destino_deben_ser_distintos_422(client):
    ef, _ = _par(client)
    r = _transferir(client, ef, ef)
    assert r.status_code == 422 and r.json() == {"detail": "Elige dos cuentas distintas"}
    assert _saldo(client, ef) == 100000 and client.get(URL, headers=A).json() == []


def test_inv049_saldo_insuficiente_en_origen_409_y_no_mueve_nada(client):
    ef, ah = _par(client, saldo_origen=10000)
    r = _transferir(client, ef, ah, 40000)
    assert r.status_code == 409 and "Saldo insuficiente" in r.json()["detail"]
    assert (_saldo(client, ef), _saldo(client, ah)) == (10000, 0) and client.get(URL, headers=A).json() == []
    assert _transferir(client, ef, ah, 10000).status_code == 200                       # justo el saldo: se permite
    assert _saldo(client, ef) == 0


def test_inv049_desde_una_tarjeta_de_credito_se_permite_quedar_negativa(client):
    tc = _cuenta(client, "Visa", "tarjeta_credito", 0)
    ef = _cuenta(client, "Efectivo", "efectivo", 0)
    assert _transferir(client, tc, ef, 30000).status_code == 200
    assert (_saldo(client, tc), _saldo(client, ef)) == (-30000, 30000)


def test_inv049_pagar_la_tarjeta_sube_su_saldo(client):
    tc = _cuenta(client, "Visa", "tarjeta_credito", -30000)
    ah = _cuenta(client, "Ahorros", "ahorros_corriente", 100000)
    assert _transferir(client, ah, tc, 30000).status_code == 200
    assert (_saldo(client, tc), _saldo(client, ah)) == (0, 70000)


def test_inv049_eliminar_transferencia_restablece_saldos(client):
    ef, ah = _par(client)
    t = _transferir(client, ef, ah, 40000).json()
    r = client.delete(f"{URL}/{t['id']}", headers=A)
    assert r.status_code == 200 and r.json() == {"message": "Transferencia eliminada"}
    assert (_saldo(client, ef), _saldo(client, ah)) == (100000, 0) and client.get(URL, headers=A).json() == []
    # si dejara el destino (que no es tarjeta) en negativo: 409 y no se borra nada
    t = _transferir(client, ef, ah, 40000).json()
    assert _transferir(client, ah, ef, 40000).status_code == 200                       # el destino gastó lo recibido
    r = client.delete(f"{URL}/{t['id']}", headers=A)
    assert r.status_code == 409 and "Saldo insuficiente" in r.json()["detail"]
    assert len(client.get(URL, headers=A).json()) == 2 and _saldo(client, ah) == 0
    assert client.delete(f"{URL}/{INEXISTENTE}", headers=A).json() == {"detail": "Transferencia no encontrada"}


def test_inv049_cuenta_archivada_no_puede_ser_origen_ni_destino(client):
    ef, ah = _par(client)
    t = _transferir(client, ef, ah, 100).json()
    for archivada in (ef, ah):
        assert client.put(f"{CUENTAS}/{archivada['id']}", json={"archivada": True}, headers=A).status_code == 200
        for origen, destino in ((ef, ah), (ah, ef)):
            r = _transferir(client, origen, destino, 1)
            assert r.status_code == 409 and "está archivada" in r.json()["detail"]
        r = client.delete(f"{URL}/{t['id']}", headers=A)                               # tampoco se elimina con una archivada
        assert r.status_code == 409 and "está archivada" in r.json()["detail"]
        assert client.put(f"{CUENTAS}/{archivada['id']}", json={"archivada": False}, headers=A).status_code == 200
    assert len(client.get(URL, headers=A).json()) == 1
    assert client.delete(f"{URL}/{t['id']}", headers=A).status_code == 200


def test_inv050_cuenta_con_transferencias_no_se_elimina_409(client):
    ef, ah = _par(client)
    assert _transferir(client, ef, ah, 100).status_code == 200
    for c in (ef, ah):
        r = client.delete(f"{CUENTAS}/{c['id']}", headers=A)
        assert r.status_code == 409 and "Archívala en lugar de eliminarla" in r.json()["detail"]
    assert len(client.get(CUENTAS, headers=A).json()) == 2


# ───────────── INV-046: cuentas y transferencias ajenas ─────────────

def test_inv046_transferencia_con_cuenta_ajena_404(client):
    mia = _cuenta(client, "Mía", saldo=1000, h=A)
    suya = _cuenta(client, "Suya", saldo=1000, h=B)
    otra_suya = _cuenta(client, "Otra", saldo=5, h=B)
    respuestas = [_transferir(client, mia, suya, 10), _transferir(client, suya, mia, 10), _transferir(client, suya, otra_suya, 10),
                  _transferir(client, mia, INEXISTENTE, 10), _transferir(client, mia, "no-es-uuid", 10)]
    assert all(r.status_code == 404 and r.json() == {"detail": "Cuenta no encontrada"} for r in respuestas)   # sin decir cuál
    assert (_saldo(client, mia), _saldo(client, suya, B)) == (1000, 1000)
    # A no ve ni borra transferencias de B
    t = _transferir(client, suya, otra_suya, 10, h=B).json()
    assert client.get(URL, headers=A).json() == [] and len(client.get(URL, headers=B).json()) == 1
    r = client.delete(f"{URL}/{t['id']}", headers=A)
    assert r.status_code == 404 and r.json() == {"detail": "Transferencia no encontrada"}
    assert client.delete(f"{URL}/no-es-uuid", headers=A).status_code == 404
    assert len(client.get(URL, headers=B).json()) == 1


# ───────────── INV-051: montos y esquema ─────────────

def test_inv051_transferencia_monto_cero_negativo_o_sobre_el_tope_422(client):
    ef, ah = _par(client, saldo_origen=5000)
    for monto in (0, -5, 12.345, 10000000000, "12.345", "0.001", "abc", "NaN", "Infinity", None, True):
        r = _transferir(client, ef, ah, monto)
        assert r.status_code == 422, (monto, r.text)
    assert client.get(URL, headers=A).json() == [] and _saldo(client, ef) == 5000
    assert _transferir(client, ef, ah, "0.01").status_code == 200                      # el mínimo
    otros = [{"fecha": "2026-02-30"}, {"fecha": "10/11/2026"}, {"fecha": "2026-11-10T10:00:00"}, {"descripcion": "x" * 256},
             {"extra": 1}, {"usuario_id": "user-b"}]
    for extra in otros:
        base = {"cuenta_origen_id": ef["id"], "cuenta_destino_id": ah["id"], "monto": 1, "fecha": "2026-11-10"}
        assert client.post(URL, json={**base, **extra}, headers=A).status_code == 422, extra
    assert len(client.get(URL, headers=A).json()) == 1


def test_inv051_el_tope_exacto_se_acepta(client):
    tc = _cuenta(client, "Visa", "tarjeta_credito", 0)
    ef = _cuenta(client, "Efectivo", "efectivo", 0)
    assert _transferir(client, tc, ef, "9999999999.99").status_code == 200
    assert _saldo(client, ef) == 9999999999.99


def test_inv047_saldo_incluye_transferencias(client):
    ef, ah = _par(client, 100000, 5000)
    assert _tx(client, ef["id"], 1000, "gasto").status_code == 200
    assert _transferir(client, ef, ah, 30000).status_code == 200
    assert _transferir(client, ah, ef, 2000).status_code == 200
    saldos = {c["nombre"]: c["saldo"] for c in client.get(CUENTAS, headers=A).json()}
    assert saldos == {"Efectivo": 100000 - 1000 - 30000 + 2000, "Ahorros": 5000 + 30000 - 2000}


def test_sin_sesion_responde_401(client):
    cuerpo = {"cuenta_origen_id": INEXISTENTE, "cuenta_destino_id": DESTINO, "monto": 1, "fecha": "2026-11-10"}
    assert client.get(URL, headers={"Authorization": "Bearer basura"}).status_code == 401
    assert client.post(URL, json=cuerpo, headers={"Authorization": "Bearer basura"}).status_code == 401
    assert client.delete(f"{URL}/{INEXISTENTE}", headers={"Authorization": "Bearer basura"}).status_code == 401
    assert client.get(URL).status_code in (401, 422)


def test_las_altas_de_transferencias_tienen_limite_por_minuto(client):
    from app.api.routes.transferencias import LIMITE_ALTAS_POR_MINUTO
    ef, ah = _par(client, saldo_origen=1000000)
    codigos = [_transferir(client, ef, ah, 1).status_code for _ in range(LIMITE_ALTAS_POR_MINUTO + 1)]
    assert codigos[:LIMITE_ALTAS_POR_MINUTO] == [200] * LIMITE_ALTAS_POR_MINUTO and codigos[-1] == 429
    ef_b, ah_b = _par(client, h=B)
    assert _transferir(client, ef_b, ah_b, 1, h=B).status_code == 200                  # el límite es por usuario


# ───────────── Rama de Supabase con cliente FALSO ─────────────

def test_inv046_supabase_usa_solo_columnas_reales_de_transferencias_y_filtra_por_el_usuario_de_la_sesion(client, monkeypatch):
    """Las columnas usadas deben existir en la tabla (checklist 9). Columnas reales de `transferencias`:
    id, usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha, descripcion, created_at."""
    def fuente(q):
        if q.tabla == "cuentas":
            return [FILA_CUENTA]
        if q.tabla == "transferencias" and q.valor("insert"):
            return [{**FILA_TRANSFERENCIA, **q.valor("insert")[0][0]}]
        if q.tabla == "transferencias":
            return [FILA_TRANSFERENCIA]
        return []
    cliente = _con_supabase_falso(monkeypatch, fuente)
    cuerpo = {"cuenta_origen_id": INEXISTENTE, "cuenta_destino_id": DESTINO, "monto": "12.50", "fecha": "2026-11-10", "descripcion": " Hola "}
    r = client.post(URL, json=cuerpo, headers=A)
    assert r.status_code == 200 and r.json()["monto"] == 12.5 and set(r.json()) == COLUMNAS_REALES
    assert client.get(URL, params={"mes": "2026-12"}, headers=A).status_code == 200
    assert client.get(URL, headers=A).status_code == 200
    assert client.delete(f"{URL}/{INEXISTENTE}", headers=A).status_code == 200
    usadas = set()
    consultas = [q for q in cliente.consultas if q.tabla == "transferencias"]
    assert len(consultas) == 5
    for q in consultas:
        for args in q.valor("select"):
            usadas |= {c for c in args[0].split(",") if c != "*"}
        for nombre in ("insert", "update"):
            for (fila,) in q.valor(nombre):
                usadas |= set(fila)
        for nombre in ("eq", "gte", "lt", "order"):
            usadas |= {a[0] for a in q.valor(nombre)}
        if not q.valor("insert"):   # toda lectura o baja filtra por el usuario de la sesión, nunca por uno ajeno
            assert ("usuario_id", "user-a") in q.valor("eq")
    assert usadas and usadas <= COLUMNAS_REALES, usadas - COLUMNAS_REALES
    insertada = next(q for q in consultas if q.valor("insert")).valor("insert")[0][0]
    assert insertada["usuario_id"] == "user-a" and insertada["monto"] == "12.50" and insertada["descripcion"] == "Hola"
    assert "created_at" not in insertada
    mensual = [q for q in consultas if q.valor("gte")][0]
    assert mensual.valor("gte") == [("fecha", "2026-12-01")] and mensual.valor("lt") == [("fecha", "2027-01-01")]
    assert mensual.valor("order") == [("fecha",), ("id",)]


@pytest.mark.parametrize("metodo, codigo, estado, texto", [
    ("post", "FZ001", 409, "Saldo insuficiente"), ("post", "FZ002", 409, "está archivada"),
    ("post", "23503", 404, "Cuenta no encontrada"), ("post", "22003", 422, "El monto es demasiado grande"),
    ("post", "23514", 422, "no cumple lo permitido"),
    ("delete", "FZ001", 409, "Saldo insuficiente"), ("delete", "FZ002", 409, "está archivada")])
def test_los_errores_de_la_bd_en_transferencias_se_traducen_sin_detalles(client, monkeypatch, capsys, metodo, codigo, estado, texto):
    def fuente(q):
        if q.tabla == "cuentas":
            return [FILA_CUENTA]
        if q.tabla == "transferencias" and (q.valor("insert") or q.valor("delete")):
            raise _ErrorPG(codigo)
        return [FILA_TRANSFERENCIA]
    _con_supabase_falso(monkeypatch, fuente)
    if metodo == "post":
        r = client.post(URL, json={"cuenta_origen_id": INEXISTENTE, "cuenta_destino_id": DESTINO, "monto": 5, "fecha": "2026-11-10"}, headers=A)
    else:
        r = client.delete(f"{URL}/{INEXISTENTE}", headers=A)
    assert r.status_code == estado and texto in r.json()["detail"]
    assert "secreto" not in r.text and "7a3f" not in r.text and "host-interno" not in r.text
    assert "secreto" not in capsys.readouterr().out                                   # tampoco en los registros


def test_los_fallos_de_la_bd_en_transferencias_son_503_sin_detalles(client, monkeypatch, capsys):
    def roto(q):
        raise RuntimeError("secreto host-interno 10.0.0.7 password=abc")
    _con_supabase_falso(monkeypatch, roto)
    cuerpo = {"cuenta_origen_id": INEXISTENTE, "cuenta_destino_id": DESTINO, "monto": 5, "fecha": "2026-11-10"}
    for r in (client.get(URL, headers=A), client.post(URL, json=cuerpo, headers=A), client.delete(f"{URL}/{INEXISTENTE}", headers=A)):
        assert r.status_code == 503 and r.json() == {"detail": MENSAJE_503} and "secreto" not in r.text
    # fallo en la escritura misma (las cuentas sí se leen): también 503 genérico, nunca 500
    def solo_falla_escribir(q):
        if q.tabla == "transferencias" and q.valor("insert"):
            raise RuntimeError("secreto host-interno")
        return [FILA_CUENTA]
    _con_supabase_falso(monkeypatch, solo_falla_escribir)
    r = client.post(URL, json=cuerpo, headers=A)
    assert r.status_code == 503 and r.json() == {"detail": MENSAJE_503}
    assert "secreto" not in capsys.readouterr().out
    # respuestas inesperadas = 503 (nunca se «dejan pasar»)
    for basura in ({"no": "lista"}, [{"id": "x"}]):
        _con_supabase_falso(monkeypatch, lambda q, b=basura: b)
        assert client.get(URL, headers=A).status_code == 503


def test_la_lista_nunca_devuelve_transferencias_de_otro_usuario_aunque_la_bd_las_envie(client, monkeypatch):
    _con_supabase_falso(monkeypatch, lambda q: [{**FILA_TRANSFERENCIA, "usuario_id": "user-b"}])
    assert client.get(URL, headers=A).status_code == 503


def test_sin_hueco_en_el_ejecutor_de_cuentas_503_inmediato_sin_encolar(client, monkeypatch):
    from app.models import cuentas as cuentas_mod
    llamadas = []
    _con_supabase_falso(monkeypatch, lambda q: llamadas.append(q.tabla) or [FILA_CUENTA])
    tomados = 0
    while cuentas_mod._huecos.acquire(blocking=False):
        tomados += 1
    try:
        inicio = time.monotonic()
        cuerpo = {"cuenta_origen_id": INEXISTENTE, "cuenta_destino_id": DESTINO, "monto": 5, "fecha": "2026-11-10"}
        for r in (client.post(URL, json=cuerpo, headers=A), client.get(URL, headers=A), client.delete(f"{URL}/{INEXISTENTE}", headers=A)):
            assert r.status_code == 503 and r.json() == {"detail": MENSAJE_503}
        assert time.monotonic() - inicio < 1.0 and llamadas == []                      # inmediato y sin tocar la BD
    finally:
        for _ in range(tomados):
            cuentas_mod._huecos.release()


def test_las_transferencias_usan_el_ejecutor_propio_de_cuentas(client, monkeypatch):
    import threading
    hilos = []

    def fuente(q):
        hilos.append(threading.current_thread().name)
        return [FILA_TRANSFERENCIA]
    _con_supabase_falso(monkeypatch, fuente)
    assert client.get(URL, headers=A).status_code == 200
    assert hilos and all(h.startswith("cuentas") and "auth-estado" not in h for h in hilos)
