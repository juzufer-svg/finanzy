"""CHG-019 fase (a), cierre de huecos · INV-029, INV-046, INV-050 · CT-009 · CT-012.

Un movimiento creado por WhatsApp puede recibir una cuenta de dinero desde la app. «Deshacer» y «corregir» no deben
dejar la cuenta en negativo ni tocar una archivada: la BD (FZ001/FZ002) rechaza el cambio y WhatsApp lo explica en español,
sin cambiar nada y sin datos de la BD en la respuesta.
"""
import pytest

import test_whatsapp as tw
from app.models import plataapp as modelos
from app.models.demo_db import ErrorBD
from conftest import auth_header

meta = tw.meta   # fixture compartida: WhatsApp configurado y Claude simulado
A = auth_header("user-a")


def _cuenta(client, saldo=0, nombre="Efectivo"):
    r = client.post("/api/v1/cuentas", json={"nombre": nombre, "tipo": "efectivo", "saldo_inicial": saldo}, headers=A)
    assert r.status_code == 200, r.text
    return r.json()


def _asignar(client, tx, cuenta_id):
    body = {"categoria_id": "", "monto": tx["monto"], "descripcion": tx.get("descripcion") or "", "fecha": tx["fecha"],
            "tipo": tx["tipo"], "cuenta_id": cuenta_id}
    r = client.put(f"/api/v1/transacciones/{tx['id']}", json=body, headers=A)
    assert r.status_code == 200, r.text


def _ingreso_de_whatsapp_con_cuenta_usada(client, meta, extra=0):
    """Ingreso de 50 000 registrado por WhatsApp, asignado a una cuenta sin colchón (saldo inicial 0) y con un gasto
    de 40 000 después: borrarlo o bajarlo a menos de 40 000 dejaría la cuenta en negativo."""
    tw._enlazar(client, meta)
    meta["claude"].append(tw.herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "ingreso", "monto": 50000, "fecha": "2026-11-23"}]}))
    tw._msg(client, "me pagaron 50 mil")
    ingreso = tw._tx(client)[0]
    cuenta = _cuenta(client)
    _asignar(client, ingreso, cuenta["id"])
    r = client.post("/api/v1/transacciones", json={"categoria_id": "", "monto": 40000 + extra, "descripcion": "g",
                                                  "fecha": "2026-11-24", "tipo": "gasto", "cuenta_id": cuenta["id"]}, headers=A)
    assert r.status_code == 200, r.text
    return ingreso, cuenta


def _estado(client):
    return sorted((t["tipo"], float(t["monto"])) for t in tw._tx(client))


def test_deshacer_un_ingreso_en_cuenta_sin_colchon_explica_y_no_borra_nada(client, meta):
    _ingreso_de_whatsapp_con_cuenta_usada(client, meta)
    antes = _estado(client)
    meta["claude"].append(tw.herramienta("deshacer_ultimo", {}))
    tw._msg(client, "deshacer")
    texto = meta["enviados"][-1][1]
    assert texto.startswith("No pude deshacerlo") and "saldo negativo" in texto and "No cambié nada" in texto
    assert "FZ001" not in texto and _estado(client) == antes
    # El movimiento sigue en el lote: tras quitar el gasto desde la app, «deshacer» ya puede borrarlo
    gasto = next(t for t in tw._tx(client) if t["tipo"] == "gasto")
    assert client.delete(f"/api/v1/transacciones/{gasto['id']}", headers=A).status_code == 200
    meta["claude"].append(tw.herramienta("deshacer_ultimo", {}))
    tw._msg(client, "deshacer")
    assert "Deshecho" in meta["enviados"][-1][1] and tw._tx(client) == []


def test_corregir_que_dejaria_saldo_negativo_explica_y_no_cambia_nada(client, meta):
    _ingreso_de_whatsapp_con_cuenta_usada(client, meta)
    antes = _estado(client)
    meta["claude"].append(tw.herramienta("corregir_ultimo", {"monto": 10000}))
    tw._msg(client, "no, eran 10 mil")
    texto = meta["enviados"][-1][1]
    assert texto.startswith("No pude corregirlo") and "saldo negativo" in texto and _estado(client) == antes


def test_cuenta_archivada_deshacer_y_corregir_explican_y_no_cambian_nada(client, meta):
    ingreso, cuenta = _ingreso_de_whatsapp_con_cuenta_usada(client, meta)
    gasto = next(t for t in tw._tx(client) if t["tipo"] == "gasto")
    assert client.delete(f"/api/v1/transacciones/{gasto['id']}", headers=A).status_code == 200
    assert client.put(f"/api/v1/cuentas/{cuenta['id']}", json={"archivada": True}, headers=A).status_code == 200
    antes = _estado(client)
    meta["claude"].append(tw.herramienta("deshacer_ultimo", {}))
    tw._msg(client, "deshacer")
    assert "No pude deshacerlo" in meta["enviados"][-1][1] and "archivada" in meta["enviados"][-1][1]
    meta["claude"].append(tw.herramienta("corregir_ultimo", {"monto": 60000}))
    tw._msg(client, "eran 60 mil")
    assert "No pude corregirlo" in meta["enviados"][-1][1] and "archivada" in meta["enviados"][-1][1]
    assert _estado(client) == antes


def test_deshacer_un_lote_con_dos_movimientos_en_cuenta_no_borra_nada(client, meta):
    tw._enlazar(client, meta)
    meta["claude"].append(tw.herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "ingreso", "monto": 1000, "fecha": "2026-11-23"}, {"tipo": "ingreso", "monto": 2000, "fecha": "2026-11-23"}]}))
    tw._msg(client, "dos ingresos")
    cuenta = _cuenta(client)
    for t in tw._tx(client):
        _asignar(client, t, cuenta["id"])
    antes = _estado(client)
    meta["claude"].append(tw.herramienta("deshacer_ultimo", {}))
    tw._msg(client, "deshacer")
    assert "No pude deshacerlo" in meta["enviados"][-1][1] and _estado(client) == antes


def test_sin_cuenta_deshacer_y_corregir_funcionan_igual_y_el_mensaje_queda_procesado(client, meta):
    tw._enlazar(client, meta)
    meta["claude"].append(tw.herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "ingreso", "monto": 1000, "fecha": "2026-11-23"}]}))
    tw._msg(client, "mil")
    meta["claude"].append(tw.herramienta("corregir_ultimo", {"monto": 3000}))
    tw._msg(client, "eran 3 mil")
    assert _estado(client) == [("ingreso", 3000.0)] and "Corregido" in meta["enviados"][-1][1]
    meta["claude"].append(tw.herramienta("deshacer_ultimo", {}))
    r = tw._webhook(client, [("wamid.fijo", tw.TEL_A, "deshacer")])
    assert r.status_code == 200 and tw._tx(client) == []
    # INV-029: Meta reenvía el mismo mensaje y NO se procesa de nuevo (no se llama a Claude otra vez)
    assert tw._webhook(client, [("wamid.fijo", tw.TEL_A, "deshacer")]).status_code == 200 and meta["claude"] == []


@pytest.mark.parametrize("codigo, fragmento", [("FZ001", "saldo negativo"), ("FZ002", "archivada")])
def test_m2_deshacer_a_medias_no_dice_no_cambie_nada_y_manda_a_revisar_la_app(client, meta, monkeypatch, codigo, fragmento):
    """Si ya se borró algún movimiento del lote y otro lo rechaza la regla de cuentas (FZ001/FZ002), el lote quedó a medias."""
    tw._enlazar(client, meta)
    meta["claude"].append(tw.herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "gasto", "monto": 1000, "fecha": "2026-11-23"}, {"tipo": "gasto", "monto": 2000, "fecha": "2026-11-23"}]}))
    tw._msg(client, "dos gastos")
    original, llamadas = modelos.TransaccionDB.eliminar, []

    async def eliminar(tid, uid):
        llamadas.append(tid)
        if len(llamadas) == 2:
            raise ErrorBD(codigo)
        return await original(tid, uid)
    monkeypatch.setattr(modelos.TransaccionDB, "eliminar", staticmethod(eliminar))
    meta["claude"].append(tw.herramienta("deshacer_ultimo", {}))
    tw._msg(client, "deshacer")
    texto = meta["enviados"][-1][1]
    assert "Deshice parte del lote" in texto and fragmento in texto and "revisa en la app" in texto.lower()
    assert "No cambié nada" not in texto and codigo not in texto
    assert len(tw._tx(client)) == 1                       # una se borró y la otra sigue


def test_un_error_de_bd_que_no_es_de_cuentas_sigue_avisando_sin_detalles(client, meta, monkeypatch):
    tw._enlazar(client, meta)
    meta["claude"].append(tw.herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "gasto", "monto": 1000, "fecha": "2026-11-23"}]}))
    tw._msg(client, "mil")

    async def explota(*_a, **_k):
        raise RuntimeError("detalle interno con 573001112233")

    monkeypatch.setattr(modelos.TransaccionDB, "eliminar", staticmethod(explota))
    meta["claude"].append(tw.herramienta("deshacer_ultimo", {}))
    tw._msg(client, "deshacer")
    assert "error del servidor" in meta["enviados"][-1][1] and "573001112233" not in meta["enviados"][-1][1]


# ── 503 genérico si la BD falla al escribir transacciones (BL-043) ────────────────────────────────

class _ClienteRoto:
    def table(self, *_):
        raise RuntimeError("detalle interno: password=secreto host=db.interno")


@pytest.fixture
def bd_rota(monkeypatch):
    monkeypatch.setattr(modelos, "_supabase_ok", lambda: True)
    monkeypatch.setattr(modelos.SupabaseDB, "get_client", staticmethod(lambda: _ClienteRoto()))


def test_503_generico_al_crear_actualizar_y_eliminar_si_la_bd_falla(client, bd_rota, monkeypatch):
    cuerpo = {"categoria_id": "", "monto": 1000, "descripcion": "x", "fecha": "2026-11-22", "tipo": "gasto"}
    r = client.post("/api/v1/transacciones", json=cuerpo, headers=A)
    assert r.status_code == 503 and "secreto" not in r.text and "RuntimeError" not in r.text
    existente = {"id": "t1", "usuario_id": "user-a", **cuerpo}

    async def obtener(*_a, **_k):
        return existente

    monkeypatch.setattr(modelos.TransaccionDB, "obtener_por_id", staticmethod(obtener))
    for r in (client.put("/api/v1/transacciones/t1", json=cuerpo, headers=A),
              client.delete("/api/v1/transacciones/t1", headers=A)):
        assert r.status_code == 503 and "secreto" not in r.text and "RuntimeError" not in r.text


def test_los_errores_de_cuentas_siguen_traduciendose_a_409(client, monkeypatch):
    async def rechaza(*_a, **_k):
        raise ErrorBD("FZ001")

    monkeypatch.setattr(modelos.TransaccionDB, "crear", staticmethod(rechaza))
    r = client.post("/api/v1/transacciones", json={"categoria_id": "", "monto": 1, "descripcion": "x",
                                                  "fecha": "2026-11-22", "tipo": "gasto"}, headers=A)
    assert r.status_code == 409 and "Saldo insuficiente" in r.json()["detail"]

