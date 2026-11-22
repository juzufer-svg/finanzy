"""CHG-004 · INV-008: abono atómico con la función SQL `abonar_meta` (BDD-METAS).

La concurrencia real se probó contra PostgreSQL (30 abonos simultáneos → suma exacta);
ver work/changes/CHG-004-abono-atomico.md. Aquí se prueba cómo el backend usa la función.
"""
import asyncio

import pytest
from postgrest.exceptions import APIError

from app.models import plataapp as modelos
from app.models.plataapp import AbonoAtomicoNoDisponible, MetaDB
from conftest import auth_header

A = auth_header("user-a")
ABONO = {"monto": 50, "fecha": "2026-11-22", "descripcion": "Quincena"}


class _Rpc:
    def __init__(self, respuesta=None, error=None):
        self.llamadas = []
        self.respuesta, self.error = respuesta, error

    def rpc(self, nombre, params):
        self.llamadas.append((nombre, params))
        return self

    def execute(self):
        if self.error:
            raise self.error
        return type("R", (), {"data": self.respuesta})()


def _con_supabase(monkeypatch, cliente):
    monkeypatch.setattr(modelos, "_supabase_ok", lambda: True)
    monkeypatch.setattr(modelos.SupabaseDB, "get_client", staticmethod(lambda: cliente))


def test_abono_usa_la_funcion_sql_con_el_dueno_del_token(monkeypatch):
    meta = {"id": "m1", "usuario_id": "user-a", "monto_actual": 150, "monto_objetivo": 1000, "nombre": "Viaje"}
    cliente = _Rpc(respuesta=[meta])
    _con_supabase(monkeypatch, cliente)
    assert asyncio.run(MetaDB.abonar("m1", "user-a", 50, "2026-11-22", "Quincena")) == meta
    assert cliente.llamadas == [("abonar_meta", {"p_meta_id": "m1", "p_usuario_id": "user-a", "p_monto": 50,
                                                 "p_fecha": "2026-11-22", "p_descripcion": "Quincena"})]


def test_meta_ajena_o_inexistente_devuelve_none(monkeypatch):
    _con_supabase(monkeypatch, _Rpc(error=APIError({"code": "P0002", "message": "meta_no_encontrada"})))
    assert asyncio.run(MetaDB.abonar("m1", "user-b", 50, "2026-11-22", "x")) is None


@pytest.mark.parametrize("codigo", ["PGRST202", "42883"])
def test_si_la_funcion_no_esta_instalada_se_avisa_para_usar_el_metodo_anterior(monkeypatch, codigo):
    _con_supabase(monkeypatch, _Rpc(error=APIError({"code": codigo, "message": "Could not find the function"})))
    with pytest.raises(AbonoAtomicoNoDisponible):
        asyncio.run(MetaDB.abonar("m1", "user-a", 50, "2026-11-22", "x"))


def test_otros_errores_de_la_bd_se_propagan(monkeypatch):
    _con_supabase(monkeypatch, _Rpc(error=APIError({"code": "57014", "message": "timeout"})))
    with pytest.raises(APIError):
        asyncio.run(MetaDB.abonar("m1", "user-a", 50, "2026-11-22", "x"))


def test_ruta_devuelve_la_meta_con_porcentaje(client, monkeypatch):
    async def abonar(meta_id, usuario_id, monto, fecha, descripcion):
        assert (meta_id, usuario_id, monto) == ("m1", "user-a", 50)
        return {"id": "m1", "usuario_id": "user-a", "nombre": "Viaje", "monto_objetivo": 200,
                "monto_actual": 50, "fecha_objetivo": "2027-01-01"}

    monkeypatch.setattr(MetaDB, "abonar", staticmethod(abonar))
    r = client.post("/api/v1/metas/m1/abonar", json=ABONO, headers=A)
    assert r.status_code == 200 and r.json()["porcentaje_completado"] == 25


def test_ruta_meta_ajena_responde_404(client, monkeypatch):
    async def abonar(*_):
        return None

    monkeypatch.setattr(MetaDB, "abonar", staticmethod(abonar))
    assert client.post("/api/v1/metas/m1/abonar", json=ABONO, headers=A).status_code == 404


def test_ruta_error_de_bd_responde_500_sin_usar_el_metodo_anterior(client, monkeypatch):
    async def abonar(*_):
        raise RuntimeError("BD caída")

    async def no_debe_llamarse(*_a, **_k):
        raise AssertionError("no debe registrar el gasto por separado")

    monkeypatch.setattr(MetaDB, "abonar", staticmethod(abonar))
    monkeypatch.setattr(modelos.TransaccionDB, "crear", staticmethod(no_debe_llamarse))
    assert client.post("/api/v1/metas/m1/abonar", json=ABONO, headers=A).status_code == 500
