"""CHG-027 · INV-063 · CT-003 y CT-012 §Transferencias: rango de fechas de transacciones y transferencias.

Solo se admiten fechas entre el 2026-01-01 y «hoy + 365 días» (día de Colombia). Todas las pruebas usan un reloj controlado:
`rango_fechas.hoy_colombia` (la fuente que usa la regla) o, para el borde Colombia/UTC, el instante UTC de `contadores`.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

import test_whatsapp as tw
from app.models import contadores, plataapp as modelos
from app.utils import rango_fechas, whatsapp as wa
from test_cuentas import A, _tx
from test_cuentas_integracion import _confirmar, _fecha_de, _recurrente, _txs
from test_transferencias import _par, _transferir

meta = tw.meta   # fixture compartida: WhatsApp configurado y Claude simulado
HOY = date(2026, 11, 25)
MAXIMA = HOY + timedelta(days=365)   # 2027-11-25
MSG = "La fecha debe estar entre el 1 de enero de 2026 y el 25/11/2027"


@pytest.fixture
def hoy(monkeypatch):
    monkeypatch.setattr(rango_fechas, "hoy_colombia", lambda: HOY)
    return HOY


def _crear(client, fecha, **extra):
    return _tx(client, None, fecha=fecha, **extra)


# ───────────── Bordes al crear una transacción ─────────────

def test_inv063_crear_transaccion_2025_12_31_se_rechaza_con_mensaje(client, hoy):
    r = _crear(client, "2025-12-31")
    assert r.status_code == 422 and MSG in r.text
    assert client.get("/api/v1/transacciones", headers=A).json() == []


def test_inv063_crear_transaccion_2026_01_01_se_acepta(client, hoy):
    assert _crear(client, "2026-01-01").status_code == 200


def test_inv063_crear_transaccion_hoy_mas_365_se_acepta(client, hoy):
    assert _crear(client, MAXIMA.isoformat()).status_code == 200


def test_inv063_crear_transaccion_hoy_mas_366_se_rechaza(client, hoy):
    r = _crear(client, (MAXIMA + timedelta(days=1)).isoformat())
    assert r.status_code == 422 and MSG in r.text


@pytest.mark.parametrize("fecha", ["9999-12-31", "0001-01-01", "2099-12-15", "2025-06-01"])
def test_inv063_crear_transaccion_fechas_absurdas_se_rechazan(client, hoy, fecha):
    r = _crear(client, fecha)
    assert r.status_code == 422 and MSG in r.text


@pytest.mark.parametrize("fecha", ["2099-02-30", "2025-02-30", "2099-04-31", "2026-02-30"])
def test_inv063_un_dia_que_no_existe_no_evade_el_rango_al_crear(client, hoy, fecha):
    r = _crear(client, fecha)
    assert r.status_code == 422 and MSG in r.text
    assert client.get("/api/v1/transacciones", headers=A).json() == []


def test_inv063_un_dia_que_no_existe_no_evade_el_rango_al_editar(client, hoy):
    tx = _vieja()
    for fecha in ("2099-02-30", "2025-02-30", "2099-04-31"):
        r = _editar(client, tx, fecha=fecha)
        assert r.status_code == 422 and MSG in r.text, fecha
    assert str(client.get(f"/api/v1/transacciones/{tx['id']}", headers=A).json()["fecha"])[:10] == "2025-06-01"


def test_inv063_la_fecha_con_hora_se_juzga_por_su_dia(client, hoy):
    assert _crear(client, "2026-01-01T00:00:00").status_code == 200
    assert _crear(client, "2025-12-31T23:59:59").status_code == 422


@pytest.mark.parametrize("fecha", ["2026-13-01", "26-01-01", "hola", "2026-1-1", ""])
def test_inv063_formato_invalido_sigue_siendo_422_como_antes(client, hoy, fecha):
    r = _crear(client, fecha)
    assert r.status_code == 422 and MSG not in r.text   # lo rechaza el patrón, no la regla de rango


def test_inv063_el_borde_depende_del_dia_de_colombia_y_no_del_dia_utc(client, monkeypatch):
    # 03:30 UTC del 26 = 22:30 del 25 en Colombia: «hoy» es el 25 (UTC diría 26)
    monkeypatch.setattr(contadores, "_ahora_utc", lambda: datetime(2026, 11, 26, 3, 30, tzinfo=timezone.utc))
    assert contadores.hoy_colombia() == date(2026, 11, 25)
    assert _crear(client, "2027-11-25").status_code == 200
    r = _crear(client, "2027-11-26")   # sería válida con el día UTC
    assert r.status_code == 422 and MSG in r.text
    # 05:00 UTC del 26 = 00:00 del 26 en Colombia: el borde ya avanzó un día
    monkeypatch.setattr(contadores, "_ahora_utc", lambda: datetime(2026, 11, 26, 5, 0, tzinfo=timezone.utc))
    assert _crear(client, "2027-11-26").status_code == 200
    assert "26/11/2027" in _crear(client, "2027-11-27").text


def test_inv063_la_ventana_se_mueve_con_el_reloj(client, monkeypatch):
    monkeypatch.setattr(rango_fechas, "hoy_colombia", lambda: date(2026, 1, 1))
    assert _crear(client, "2027-01-01").status_code == 200
    assert _crear(client, "2027-01-02").status_code == 422


# ───────────── Editar una transacción ─────────────

def _vieja(fecha="2025-06-01"):
    """Una transacción guardada ANTES de la regla (fuera del rango actual); se inserta sin pasar por la API."""
    return asyncio.run(modelos.TransaccionDB.crear(usuario_id="user-a", categoria_id="", monto=1000, descripcion="vieja",
                                                   fecha=fecha, tipo="gasto", medio_pago=None, cuenta_id=None))


def _editar(client, tx, **cambios):
    cuerpo = {"categoria_id": "", "monto": tx["monto"], "descripcion": "x", "fecha": str(tx["fecha"])[:10], "tipo": tx["tipo"], **cambios}
    return client.put(f"/api/v1/transacciones/{tx['id']}", json=cuerpo, headers=A)


def test_inv063_editar_sin_cambiar_la_fecha_no_se_rechaza_aunque_este_fuera_de_rango(client, hoy):
    tx = _vieja()
    r = _editar(client, tx, monto=2500, descripcion="corregida")
    assert r.status_code == 200 and r.json()["monto"] == 2500 and str(r.json()["fecha"])[:10] == "2025-06-01"


def test_inv063_editar_cambiando_la_fecha_a_otra_fuera_de_rango_se_rechaza(client, hoy):
    tx = _vieja()
    for fecha in ("2025-12-31", (MAXIMA + timedelta(days=1)).isoformat(), "9999-01-01"):
        r = _editar(client, tx, fecha=fecha)
        assert r.status_code == 422 and MSG in r.text, fecha
    assert str(client.get(f"/api/v1/transacciones/{tx['id']}", headers=A).json()["fecha"])[:10] == "2025-06-01"


def test_inv063_editar_cambiando_la_fecha_a_una_dentro_del_rango_se_acepta(client, hoy):
    tx = _vieja()
    assert _editar(client, tx, fecha="2026-01-01").status_code == 200
    assert _editar(client, tx, fecha=MAXIMA.isoformat()).status_code == 200


def test_inv063_editar_una_transaccion_valida_con_fecha_nueva_fuera_de_rango_se_rechaza(client, hoy):
    tx = _crear(client, "2026-05-01").json()
    assert _editar(client, tx, monto=1500).status_code == 200
    assert _editar(client, tx, fecha="2025-12-31").status_code == 422
    assert _editar(client, tx, fecha=(MAXIMA + timedelta(days=1)).isoformat()).status_code == 422


def test_inv063_editar_ajena_sigue_siendo_404_antes_que_el_rango(client, hoy):
    from conftest import auth_header
    tx = _crear(client, "2026-05-01").json()
    r = client.put(f"/api/v1/transacciones/{tx['id']}", headers=auth_header("user-b"),
                   json={"categoria_id": "", "monto": 1, "descripcion": "x", "fecha": "2025-01-01", "tipo": "gasto"})
    assert r.status_code == 404


# ───────────── Transferencias ─────────────

def test_inv063_transferencia_bordes_inferior_y_superior(client, hoy):
    ef, ah = _par(client, saldo_origen=1_000_000)
    for fecha in ("2025-12-31", (MAXIMA + timedelta(days=1)).isoformat(), "9999-12-31", "0001-01-01"):
        r = _transferir(client, ef, ah, 1000, fecha=fecha)
        assert r.status_code == 422 and MSG in r.text, fecha
    assert client.get("/api/v1/transferencias", headers=A).json() == []
    assert _transferir(client, ef, ah, 1000, fecha="2026-01-01").status_code == 200
    assert _transferir(client, ef, ah, 1000, fecha=MAXIMA.isoformat()).status_code == 200


def test_inv063_transferencia_con_fecha_inexistente_sigue_siendo_422(client, hoy):
    ef, ah = _par(client)
    r = _transferir(client, ef, ah, 1000, fecha="2026-02-30")
    assert r.status_code == 422 and "no existe" in r.text and MSG not in r.text


def test_inv063_transferencia_usa_el_dia_de_colombia(client, monkeypatch):
    monkeypatch.setattr(contadores, "_ahora_utc", lambda: datetime(2026, 11, 26, 3, 30, tzinfo=timezone.utc))
    ef, ah = _par(client)
    assert _transferir(client, ef, ah, 1000, fecha="2027-11-25").status_code == 200
    assert _transferir(client, ef, ah, 1000, fecha="2027-11-26").status_code == 422


# ───────────── Confirmar recurrentes ─────────────

def test_inv063_confirmar_recurrente_en_rango_sigue_funcionando(client, hoy):
    rec = _recurrente(client, proxima_fecha="2026-11-05")
    r = _confirmar(client, rec, ocurrencia="2026-11-05")
    assert r.status_code == 200 and _fecha_de(client, rec) == "2026-12-05" and len(_txs(client)) == 1


def test_inv063_confirmar_con_ocurrencia_fuera_de_rango_422_y_la_fecha_no_avanza(client, hoy):
    rec = _recurrente(client, proxima_fecha="2025-12-31")   # las recurrentes no se tocan: ya existía así
    r = _confirmar(client, rec, ocurrencia="2025-12-31")
    assert r.status_code == 422 and MSG in r.text
    assert _fecha_de(client, rec) == "2025-12-31" and _txs(client) == []


def test_inv063_confirmar_con_fecha_ajustada_fuera_de_rango_422_y_la_fecha_no_avanza(client, hoy):
    rec = _recurrente(client, proxima_fecha="2026-11-05")
    for fecha in ("2025-12-31", (MAXIMA + timedelta(days=1)).isoformat()):
        r = _confirmar(client, rec, ocurrencia="2026-11-05", fecha=fecha)
        assert r.status_code == 422 and MSG in r.text, fecha
    assert _fecha_de(client, rec) == "2026-11-05" and _txs(client) == []
    assert _confirmar(client, rec, ocurrencia="2026-11-05", fecha="2026-01-01").status_code == 200


# ───────────── WhatsApp ─────────────

@pytest.fixture
def reloj_wa(monkeypatch):
    """El día de hoy fijo (2026-06-15) tanto para WhatsApp como para la regla de rango."""
    class Falso(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(wa, "datetime", Falso)
    monkeypatch.setattr(rango_fechas, "hoy_colombia", lambda: date(2026, 6, 15))


def _registrar_por_whatsapp(client, meta, fecha):
    tw._enlazar(client, meta)
    meta["claude"].append(tw.herramienta("registrar_movimientos", {"movimientos": [{"tipo": "gasto", "monto": 1000, "fecha": fecha}]}))
    tw._msg(client, "mil pesos")


def test_inv063_whatsapp_fecha_anterior_a_2026_no_registra_y_responde_mensaje_fijo(client, meta, reloj_wa):
    _registrar_por_whatsapp(client, meta, "2025-12-31")   # dentro de los 366 días de antes, pero antes del 2026-01-01
    assert tw._tx(client) == []
    assert meta["enviados"][-1][1] == "La fecha está fuera del rango permitido"


def test_inv063_whatsapp_fecha_valida_sigue_registrandose(client, meta, reloj_wa):
    _registrar_por_whatsapp(client, meta, "2026-01-01")
    assert [t["fecha"] for t in tw._tx(client)] == ["2026-01-01"]


@pytest.mark.parametrize("fecha", ["2030-01-01", "2020-01-01", "ayer", "9999-12-31"])
def test_inv063_whatsapp_fechas_absurdas_siguen_guardandose_como_hoy(client, meta, reloj_wa, fecha):
    _registrar_por_whatsapp(client, meta, fecha)
    assert [t["fecha"] for t in tw._tx(client)] == ["2026-06-15"]


def test_inv063_whatsapp_corregir_a_una_fecha_anterior_a_2026_no_cambia_nada(client, meta, reloj_wa):
    _registrar_por_whatsapp(client, meta, "2026-06-10")
    meta["claude"].append(tw.herramienta("corregir_ultimo", {"fecha": "2025-12-31"}))
    tw._msg(client, "no, fue en diciembre")
    assert meta["enviados"][-1][1] == "La fecha está fuera del rango permitido"
    assert [t["fecha"] for t in tw._tx(client)] == ["2026-06-10"]
