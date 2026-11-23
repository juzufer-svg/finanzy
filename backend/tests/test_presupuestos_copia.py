"""CHG-012 · REQ-F-007 CA-4: copiar los presupuestos del mes anterior (BDD-PRESUPUESTOS)."""
from conftest import auth_header

A = auth_header("user-a")
B = auth_header("user-b")


def _categoria(client, nombre, headers=A):
    return client.post("/api/v1/categorias", json={"nombre": nombre, "tipo": "gasto"}, headers=headers).json()["id"]


def _presupuesto(client, categoria_id, limite, mes, headers=A):
    body = {"categoria_id": categoria_id, "limite_mensual": limite, "mes_ano": mes}
    assert client.post("/api/v1/presupuestos", json=body, headers=headers).status_code == 200


def _copiar(client, desde="2026-10", hacia="2026-11", headers=A):
    return client.post("/api/v1/presupuestos/copiar", json={"desde": desde, "hacia": hacia}, headers=headers)


def test_copia_todos_los_presupuestos_al_mes_destino(client):
    comida, transporte = _categoria(client, "Comida"), _categoria(client, "Transporte")
    _presupuesto(client, comida, 800_000, "2026-10")
    _presupuesto(client, transporte, 200_000, "2026-10")
    r = _copiar(client)
    assert r.status_code == 200
    assert (r.json()["copiados"], r.json()["omitidos"]) == (2, 0)
    nov = client.get("/api/v1/presupuestos/2026-11", headers=A).json()
    assert sorted((p["categoria_id"], p["limite_mensual"]) for p in nov) == sorted([(comida, 800_000), (transporte, 200_000)])
    # El mes de origen no cambia
    assert len(client.get("/api/v1/presupuestos/2026-10", headers=A).json()) == 2


def test_no_reemplaza_ni_duplica_los_que_ya_existen(client):
    comida, ocio = _categoria(client, "Comida"), _categoria(client, "Ocio")
    _presupuesto(client, comida, 800_000, "2026-10")
    _presupuesto(client, ocio, 100_000, "2026-10")
    _presupuesto(client, comida, 950_000, "2026-11")  # la persona ya lo ajustó para noviembre
    r = _copiar(client).json()
    assert (r["copiados"], r["omitidos"]) == (1, 1)
    nov = {p["categoria_id"]: p["limite_mensual"] for p in r["presupuestos"]}
    assert nov == {comida: 950_000, ocio: 100_000}
    # Repetir la copia no crea duplicados
    again = _copiar(client).json()
    assert (again["copiados"], again["omitidos"]) == (0, 2) and len(again["presupuestos"]) == 2


def test_mes_sin_presupuestos_no_copia_nada(client):
    r = _copiar(client).json()
    assert r == {"copiados": 0, "omitidos": 0, "presupuestos": []}


def test_inv001_solo_copia_los_propios(client):
    ajena = _categoria(client, "Ajena", headers=B)
    _presupuesto(client, ajena, 500_000, "2026-10", headers=B)
    assert _copiar(client).json()["copiados"] == 0
    assert client.get("/api/v1/presupuestos/2026-11", headers=A).json() == []
    assert client.get("/api/v1/presupuestos/2026-11", headers=B).json() == []


def test_meses_invalidos_o_iguales_son_422(client):
    assert _copiar(client, desde="2026-13").status_code == 422
    assert _copiar(client, hacia="noviembre").status_code == 422
    r = _copiar(client, desde="2026-11", hacia="2026-11")
    assert r.status_code == 422 and "distintos" in r.json()["detail"]
