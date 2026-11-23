"""CHG-013 · INV-028: sin categorías ni presupuestos repetidos."""
import pytest

from app.models import plataapp as modelos
from conftest import auth_header

A = auth_header("user-a")
B = auth_header("user-b")


def _cat(client, nombre, tipo="gasto", headers=A):
    return client.post("/api/v1/categorias", json={"nombre": nombre, "tipo": tipo}, headers=headers)


@pytest.mark.parametrize("repetido", ["Mercado", "mercado", "  MERCADO ", "Mercado  "])
def test_inv028_no_se_repite_una_categoria_del_mismo_tipo(client, repetido):
    assert _cat(client, "Mercado").status_code == 200
    r = _cat(client, repetido)
    assert r.status_code == 409 and r.json()["detail"] == "Ya tienes una categoría con ese nombre y tipo."


def test_mismo_nombre_con_otro_tipo_u_otra_persona_si_se_permite(client):
    assert _cat(client, "Otros", "gasto").status_code == 200
    assert _cat(client, "Otros", "ingreso").status_code == 200
    assert _cat(client, "Otros", "gasto", headers=B).status_code == 200


def test_el_nombre_se_guarda_sin_espacios_sobrantes(client):
    assert _cat(client, "  Mi   gimnasio ").json()["nombre"] == "Mi gimnasio"
    assert _cat(client, "   ").status_code == 422


def test_renombrar_a_un_nombre_existente_es_409_y_no_cambia_nada(client):
    a = _cat(client, "Mercado").json()
    b = _cat(client, "Ropa").json()
    r = client.put(f"/api/v1/categorias/{b['id']}", json={"nombre": "MERCADO", "tipo": "gasto"}, headers=A)
    assert r.status_code == 409
    # Editar la misma categoría sin cambiarle el nombre sí funciona
    ok = client.put(f"/api/v1/categorias/{a['id']}", json={"nombre": "Mercado", "tipo": "gasto", "icono": "🛒"}, headers=A)
    assert ok.status_code == 200 and ok.json()["icono"] == "🛒"


class _ErrorPostgrest(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def test_si_la_bd_rechaza_por_unique_se_responde_409(client, monkeypatch):
    async def duplicada(*args, **kwargs):
        raise _ErrorPostgrest("23505", 'duplicate key value violates unique constraint "categorias_usuario_nombre_tipo_unico"')

    monkeypatch.setattr(modelos.CategoriaDB, "crear", staticmethod(duplicada))
    assert _cat(client, "Nueva").status_code == 409


def test_otro_error_de_la_bd_no_se_confunde_con_un_duplicado(client, monkeypatch):
    """Revisión CHG-013 (H3): un error con «unique» o «23505» en el texto pero otro código no es un duplicado."""
    async def otro_error(*args, **kwargs):
        raise _ErrorPostgrest("23503", 'insert violates foreign key; Key (id)=(23505-unique) is not present')

    monkeypatch.setattr(modelos.CategoriaDB, "crear", staticmethod(otro_error))
    with pytest.raises(_ErrorPostgrest):
        _cat(client, "Nueva")


def test_se_puede_editar_el_icono_de_categorias_heredadas_parecidas(client):
    """Revisión CHG-013 (H2): «Viajes» y «viajes» heredadas (la BD las acepta) siguen siendo editables."""
    a = _cat(client, "Viajes").json()
    b = modelos.DemoCategoriaDB._categorias
    import uuid
    hid = str(uuid.uuid4())
    b[hid] = {"id": hid, "usuario_id": "user-a", "nombre": "viajes", "icono": "", "tipo": "gasto"}
    r = client.put(f"/api/v1/categorias/{hid}", json={"nombre": "viajes", "tipo": "gasto", "icono": "✈️"}, headers=A)
    assert r.status_code == 200 and r.json()["icono"] == "✈️"
    # Pero renombrar la otra para chocar sigue dando 409
    assert client.put(f"/api/v1/categorias/{a['id']}", json={"nombre": "Viajes 2", "tipo": "gasto"}, headers=A).status_code == 200
    assert client.put(f"/api/v1/categorias/{a['id']}", json={"nombre": "VIAJES", "tipo": "gasto"}, headers=A).status_code == 409


def test_inv028_un_solo_presupuesto_por_categoria_y_mes(client):
    cat = _cat(client, "Mercado").json()["id"]
    body = {"categoria_id": cat, "limite_mensual": 500, "mes_ano": "2026-11"}
    assert client.post("/api/v1/presupuestos", json=body, headers=A).status_code == 200
    r = client.post("/api/v1/presupuestos", json={**body, "limite_mensual": 900}, headers=A)
    assert r.status_code == 409 and "Edítalo" in r.json()["detail"]
    assert client.post("/api/v1/presupuestos", json={**body, "mes_ano": "2026-12"}, headers=A).status_code == 200
    assert [p["limite_mensual"] for p in client.get("/api/v1/presupuestos/2026-11", headers=A).json()] == [500]


def test_copias_simultaneas_no_duplican(client, monkeypatch):
    """Dos pestañas copian a la vez: la segunda no ve los que creó la primera, pero la BD lo impide."""
    cat = _cat(client, "Mercado").json()["id"]
    client.post("/api/v1/presupuestos", json={"categoria_id": cat, "limite_mensual": 500, "mes_ano": "2026-10"}, headers=A)
    client.post("/api/v1/presupuestos", json={"categoria_id": cat, "limite_mensual": 700, "mes_ano": "2026-11"}, headers=A)
    original = modelos.PresupuestoDB.obtener_por_usuario_mes
    vistas = {"n": 0}

    async def destino_viejo(usuario_id, mes_ano):
        vistas["n"] += 1
        if mes_ano == "2026-11" and vistas["n"] == 2:
            return []  # la lectura del destino llegó antes de la otra copia
        return await original(usuario_id, mes_ano)

    monkeypatch.setattr(modelos.PresupuestoDB, "obtener_por_usuario_mes", staticmethod(destino_viejo))
    r = client.post("/api/v1/presupuestos/copiar", json={"desde": "2026-10", "hacia": "2026-11"}, headers=A)
    assert r.status_code == 200 and r.json()["copiados"] == 0 and r.json()["omitidos"] == 1
    monkeypatch.setattr(modelos.PresupuestoDB, "obtener_por_usuario_mes", staticmethod(original))
    assert [p["limite_mensual"] for p in client.get("/api/v1/presupuestos/2026-11", headers=A).json()] == [700]
