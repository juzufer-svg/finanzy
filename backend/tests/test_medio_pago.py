"""CHG-007 · INV-022: medio de pago de las transacciones (BDD-TRANSACCIONES)."""
import asyncio

import pytest

from app.models import plataapp as modelos
from app.schemas.plataapp import MEDIOS_PAGO
from conftest import auth_header

A = auth_header("user-a")


def _tx(client, **extra):
    body = {"categoria_id": "", "monto": 10, "descripcion": "x", "fecha": "2026-11-22", "tipo": "gasto", **extra}
    return client.post("/api/v1/transacciones", json=body, headers=A)


@pytest.mark.parametrize("medio", MEDIOS_PAGO)
def test_inv022_cada_medio_permitido_se_guarda_y_se_devuelve(client, medio):
    creada = _tx(client, medio_pago=medio)
    assert creada.status_code == 200 and creada.json()["medio_pago"] == medio
    lista = client.get("/api/v1/transacciones?mes=2026-11", headers=A).json()
    assert [t["medio_pago"] for t in lista] == [medio]


@pytest.mark.parametrize("medio", ["bitcoin", "Débito", "DEBITO", "", 5])
def test_inv022_medio_no_permitido_se_rechaza(client, medio):
    assert _tx(client, medio_pago=medio).status_code == 422


def test_inv022_sin_medio_de_pago_queda_vacio(client):
    # Compatibilidad: clientes antiguos y abonos a metas no envían medio de pago
    creada = _tx(client)
    assert creada.status_code == 200 and creada.json()["medio_pago"] is None


def test_editar_sin_enviar_medio_conserva_el_que_tenia(client):
    tx = _tx(client, medio_pago="efectivo").json()
    body = {"categoria_id": "", "monto": 20, "descripcion": "y", "fecha": "2026-11-22", "tipo": "gasto"}
    editada = client.put(f"/api/v1/transacciones/{tx['id']}", json=body, headers=A)
    assert editada.status_code == 200
    assert editada.json()["medio_pago"] == "efectivo" and editada.json()["monto"] == 20


def test_editar_puede_cambiar_o_quitar_el_medio(client):
    tx = _tx(client, medio_pago="efectivo").json()
    body = {"categoria_id": "", "monto": 10, "descripcion": "x", "fecha": "2026-11-22", "tipo": "gasto"}
    cambio = client.put(f"/api/v1/transacciones/{tx['id']}", json={**body, "medio_pago": "credito"}, headers=A)
    assert cambio.json()["medio_pago"] == "credito"
    quitado = client.put(f"/api/v1/transacciones/{tx['id']}", json={**body, "medio_pago": None}, headers=A)
    assert quitado.json()["medio_pago"] is None


def test_abono_a_meta_no_exige_medio_de_pago(client):
    meta = client.post("/api/v1/metas", json={"nombre": "Viaje", "monto_objetivo": 100, "fecha_objetivo": "2027-01-01"},
                       headers=A).json()
    abono = client.post(f"/api/v1/metas/{meta['id']}/abonar", json={"monto": 10, "fecha": "2026-11-22"}, headers=A)
    assert abono.status_code == 200
    gasto = client.get("/api/v1/transacciones?mes=2026-11", headers=A).json()[0]
    assert gasto["medio_pago"] is None


# ---- Supabase: qué columnas se envían (sin base real) ----

class _Tabla:
    def __init__(self, registro):
        self.registro = registro

    def __getattr__(self, _nombre):
        return lambda *a, **k: self

    def insert(self, fila):
        self.registro["insert"] = fila
        return self

    def update(self, cambios):
        self.registro["update"] = cambios
        return self

    def execute(self):
        return type("R", (), {"data": [self.registro.get("insert") or self.registro.get("update")]})()


class _Cliente:
    def __init__(self):
        self.registro: dict = {}

    def table(self, _nombre):
        return _Tabla(self.registro)


@pytest.fixture
def supabase_falso(monkeypatch):
    cliente = _Cliente()
    monkeypatch.setattr(modelos, "_supabase_ok", lambda: True)
    monkeypatch.setattr(modelos.SupabaseDB, "get_client", staticmethod(lambda: cliente))
    return cliente.registro


def test_supabase_insert_sin_medio_no_envia_la_columna(supabase_falso):
    asyncio.run(modelos.TransaccionDB.crear("u", "", 5, "", "2026-11-22", "gasto"))
    assert "medio_pago" not in supabase_falso["insert"]


def test_supabase_insert_con_medio_lo_envia(supabase_falso):
    asyncio.run(modelos.TransaccionDB.crear("u", "", 5, "", "2026-11-22", "gasto", "debito"))
    assert supabase_falso["insert"]["medio_pago"] == "debito"


def test_supabase_update_distingue_no_enviado_de_quitar(supabase_falso):
    asyncio.run(modelos.TransaccionDB.actualizar("t", "u", monto=5))
    assert "medio_pago" not in supabase_falso["update"]
    asyncio.run(modelos.TransaccionDB.actualizar("t", "u", monto=5, medio_pago=None))
    assert supabase_falso["update"]["medio_pago"] is None


def test_supabase_update_categoria_vacia_queda_sin_categoria(supabase_falso):
    # Antes se enviaba "" a una columna uuid y Supabase respondía con error (500)
    asyncio.run(modelos.TransaccionDB.actualizar("t", "u", categoria_id="", monto=5))
    assert supabase_falso["update"]["categoria_id"] is None
