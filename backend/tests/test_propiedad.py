"""INV-001 y INV-002: cada usuario solo accede a sus propios datos. (BDD-PROPIEDAD)"""
from conftest import auth_header

A = auth_header("user-a")
B = auth_header("user-b")


def _tx(client, headers, **extra):
    body = {"categoria_id": "", "monto": 10, "descripcion": "x", "fecha": "2026-11-22", "tipo": "gasto", **extra}
    return client.post("/api/v1/transacciones", json=body, headers=headers)


def _categoria_de_a(client):
    return client.post("/api/v1/categorias", json={"nombre": "Restaurantes", "icono": "🍔", "tipo": "gasto"}, headers=A).json()


def test_inv001_otro_usuario_no_ve_edita_ni_borra_transacciones(client):
    tx = _tx(client, A).json()
    assert client.get(f"/api/v1/transacciones/{tx['id']}", headers=B).status_code == 404
    edit = {"categoria_id": "", "monto": 1, "descripcion": "hack", "fecha": "2026-11-22", "tipo": "gasto"}
    assert client.put(f"/api/v1/transacciones/{tx['id']}", json=edit, headers=B).status_code == 404
    assert client.delete(f"/api/v1/transacciones/{tx['id']}", headers=B).status_code == 404
    # el dueño sigue viendo su transacción intacta
    propia = client.get(f"/api/v1/transacciones/{tx['id']}", headers=A)
    assert propia.status_code == 200 and propia.json()["descripcion"] == "x"


def test_inv001_otro_usuario_no_modifica_categorias_presupuestos_ni_metas(client):
    cat = _categoria_de_a(client)
    pres = client.post("/api/v1/presupuestos", json={"categoria_id": cat["id"], "limite_mensual": 100, "mes_ano": "2026-11"}, headers=A).json()
    meta = client.post("/api/v1/metas", json={"nombre": "Viaje", "monto_objetivo": 1000, "fecha_objetivo": "2027-01-01"}, headers=A).json()

    assert client.put(f"/api/v1/categorias/{cat['id']}", json={"nombre": "x", "icono": "", "tipo": "gasto"}, headers=B).status_code == 404
    assert client.delete(f"/api/v1/categorias/{cat['id']}", headers=B).status_code == 404
    assert client.put(f"/api/v1/presupuestos/{pres['id']}", json={"limite_mensual": 1}, headers=B).status_code == 404
    assert client.delete(f"/api/v1/presupuestos/{pres['id']}", headers=B).status_code == 404
    assert client.put(f"/api/v1/metas/{meta['id']}", json={"monto_actual": 999}, headers=B).status_code == 404
    assert client.delete(f"/api/v1/metas/{meta['id']}", headers=B).status_code == 404
    assert client.post(f"/api/v1/metas/{meta['id']}/abonar", json={"monto": 5, "fecha": "2026-11-22"}, headers=B).status_code == 404


def test_inv001_el_dueno_si_puede_operar_sus_registros(client):
    cat = _categoria_de_a(client)
    pres = client.post("/api/v1/presupuestos", json={"categoria_id": cat["id"], "limite_mensual": 100, "mes_ano": "2026-11"}, headers=A).json()
    assert client.put(f"/api/v1/presupuestos/{pres['id']}", json={"limite_mensual": 200}, headers=A).json()["limite_mensual"] == 200
    assert client.delete(f"/api/v1/categorias/{cat['id']}", headers=A).status_code == 200


def test_inv001_listados_solo_devuelven_datos_propios(client):
    _tx(client, A)
    assert client.get("/api/v1/transacciones", headers=B).json() == []
    assert len(client.get("/api/v1/transacciones", headers=A).json()) == 1


def test_inv002_no_se_puede_usar_una_categoria_ajena(client):
    cat = _categoria_de_a(client)
    assert _tx(client, B, categoria_id=cat["id"]).status_code == 404
    pres = client.post("/api/v1/presupuestos", json={"categoria_id": cat["id"], "limite_mensual": 50, "mes_ano": "2026-11"}, headers=B)
    assert pres.status_code == 404
    # ni al editar una transacción propia
    propia = _tx(client, B).json()
    edit = {"categoria_id": cat["id"], "monto": 1, "descripcion": "", "fecha": "2026-11-22", "tipo": "gasto"}
    assert client.put(f"/api/v1/transacciones/{propia['id']}", json=edit, headers=B).status_code == 404


def test_sin_token_o_token_mal_formado_es_401(client):
    assert client.get("/api/v1/categorias", headers={"Authorization": "x"}).status_code == 401
    assert client.get("/api/v1/categorias", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/api/v1/categorias").status_code == 422  # cabecera obligatoria ausente
