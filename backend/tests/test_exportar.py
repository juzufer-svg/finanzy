"""CHG-018 · REQ-F-019 · INV-042 a INV-045 · REQ-N-019, N-020, N-026: exportar transacciones (BDD-EXPORTAR, CT-011)."""
import asyncio
import csv
import io
import random
import re
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone

import httpx
import pytest
from openpyxl import load_workbook

from app.api.routes import exportar as exportar_routes
from app.main import app
from app.models import demo_db, whatsapp as whatsapp_db
from app.models.plataapp import TransaccionDB
from app.utils import exportar as generador
from conftest import auth_header

A = auth_header("user-a")
B = auth_header("user-b")
URL = "/api/v1/exportaciones/transacciones"
ENCABEZADOS = ["Fecha", "Tipo", "Categoría", "Descripción", "Medio de pago", "Monto (COP)", "Origen", "Cuenta"]   # CT-011 v1.1: la columna 8 es nueva
PELIGROSAS = ['=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)", "\t=1", "\r=1"]
DEMASIADO_GRANDE = "exportacion_demasiado_grande"


# ── Ayudas ────────────────────────────────────────────────────────────────────

def sembrar(usuario="user-a", fecha="2026-11-10", descripcion="", monto=10.0, tipo="gasto",
            categoria_id=None, medio_pago=None, cantidad=1) -> list:
    """Inserta transacciones directo en la BD demo (rápido, sin pasar por la API). Devuelve sus ids."""
    ids = []
    for _ in range(cantidad):
        tid = str(uuid.uuid4())
        demo_db.DemoTransaccionDB._transacciones[tid] = {
            "id": tid, "usuario_id": usuario, "categoria_id": categoria_id, "monto": monto,
            "descripcion": descripcion, "fecha": fecha, "tipo": tipo, "medio_pago": medio_pago,
        }
        ids.append(tid)
    return ids


def pedir(client, headers=A, **params):
    return client.get(URL, params=params, headers=headers)


def filas_csv(r) -> list:
    assert r.content.startswith(b"\xef\xbb\xbf")
    texto = r.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(texto, newline=""), delimiter=";"))


def hoja_xlsx(r):
    return load_workbook(io.BytesIO(r.content))["Transacciones"]


def texto_aleatorio(rng, largo, alfabeto) -> str:
    return "".join(rng.choice(alfabeto) for _ in range(largo))


CJK = [chr(c) for c in range(0x4E00, 0xA000)]


def sembrar_peor_caso(cantidad=10_000, usuario="user-a"):
    """Peor caso real: descripción de 255 caracteres con comillas, varios bytes (CJK, emoji) y texto casi incompresible."""
    rng = random.Random(7)
    for i in range(cantidad):
        cuerpo = texto_aleatorio(rng, 251, CJK)
        sembrar(usuario, fecha=f"2026-11-{1 + i % 28:02d}", descripcion='"' + cuerpo + '"😀', monto=1234.5)


# ── INV-042: solo lo del usuario de la sesión ─────────────────────────────────

def test_inv042_exporta_solo_las_transacciones_del_usuario_de_la_sesion(client):
    sembrar("user-a", descripcion="de A 1")
    sembrar("user-a", descripcion="de A 2")
    sembrar("user-b", descripcion="de B SECRETA")
    r = pedir(client, A, desde="2026-11")
    descripciones = [f[3] for f in filas_csv(r)[1:]]
    assert sorted(descripciones) == ["de A 1", "de A 2"]
    assert "SECRETA" not in r.text
    assert [f[3] for f in filas_csv(pedir(client, B, desde="2026-11"))[1:]] == ["de B SECRETA"]


def test_inv042_no_acepta_usuario_en_la_peticion(client):
    sembrar("user-a", descripcion="de A")
    sembrar("user-b", descripcion="de B")
    r = client.get(URL, params={"desde": "2026-11", "usuario_id": "user-b", "user_id": "user-b"},
                   headers={**A, "X-Usuario-Id": "user-b", "X-User-Id": "user-b"})
    assert r.status_code == 200
    assert [f[3] for f in filas_csv(r)[1:]] == ["de A"]


def test_inv042_sin_sesion_responde_401(client):
    sembrar("user-a", descripcion="privada")
    sin_cabecera = client.get(URL, params={"desde": "2026-11"})
    token_malo = client.get(URL, params={"desde": "2026-11"}, headers={"Authorization": "Bearer basura"})
    for r in (sin_cabecera, token_malo):
        assert r.status_code == 401
        assert "privada" not in r.text


def test_inv042_cabeceras_no_store_y_nombre_sin_datos_personales(client, users):
    # el correo del usuario no puede aparecer en el nombre ni en ninguna cabecera
    users["persona.privada@example.com"] = {"id": "id-privada", "email": "persona.privada@example.com",
                                            "full_name": "Persona Privada", "is_active": True, "session_version": 0}
    sembrar("id-privada", descripcion="x")
    for formato, ext in (("csv", "csv"), ("xlsx", "xlsx")):
        r = pedir(client, auth_header("id-privada"), desde="2026-11", formato=formato)
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["content-disposition"] == f'attachment; filename="finanzy-transacciones-2026-11.{ext}"'
        cabeceras = " ".join(f"{k}:{v}" for k, v in r.headers.items()).lower()
        for dato in ("persona", "privada", "example.com", "id-privada"):
            assert dato not in cabeceras
    # los errores tampoco se guardan en cachés
    assert pedir(client, auth_header("id-privada"), desde="2026-13").headers["cache-control"] == "no-store"


def test_inv042_el_archivo_no_contiene_ids_ni_correo(client):
    cat = client.post("/api/v1/categorias", json={"nombre": "Comida rica", "icono": "🍔", "tipo": "gasto"}, headers=A).json()
    tid = sembrar(descripcion="almuerzo", categoria_id=cat["id"])[0]
    for formato in ("csv", "xlsx"):
        r = pedir(client, desde="2026-11", formato=formato)
        contenido = r.text if formato == "csv" else " ".join(
            str(c.value) for fila in hoja_xlsx(r).iter_rows() for c in fila)
        if formato == "xlsx":  # también el XML crudo de todas las partes del zip
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                contenido += " ".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist())
        for prohibido in (tid, cat["id"], "user-a", "@example.com"):
            assert prohibido not in contenido
        assert "Comida rica" in contenido


def test_inv042_la_categoria_ajena_no_se_filtra(client):
    ajena = client.post("/api/v1/categorias", json={"nombre": "Categoría de B", "icono": "", "tipo": "gasto"}, headers=B).json()
    sembrar("user-a", descripcion="dato corrupto", categoria_id=ajena["id"])
    for formato in ("csv", "xlsx"):
        r = pedir(client, desde="2026-11", formato=formato)
        assert "Categoría de B" not in (r.text if formato == "csv" else str(r.content))
        fila = filas_csv(r)[1] if formato == "csv" else [c.value for c in next(hoja_xlsx(r).iter_rows(min_row=2))]
        assert fila[2] == "Sin categoría"


# ── INV-043: sin inyección de fórmulas ────────────────────────────────────────

def test_inv043_csv_neutraliza_formulas(client):
    cat = client.post("/api/v1/categorias", json={"nombre": "=1+1", "icono": "", "tipo": "gasto"}, headers=A).json()
    for i, d in enumerate(PELIGROSAS):
        sembrar(descripcion=d, categoria_id=cat["id"], fecha=f"2026-11-{i + 1:02d}")
    r = pedir(client, desde="2026-11")
    filas = filas_csv(r)[1:]
    assert [f[3] for f in filas] == ["'" + d.replace("\r", "\r'") for d in PELIGROSAS]
    for f in filas:
        assert f[2] == "'=1+1"
        for texto in f[1:5] + f[6:]:   # ninguna celda de texto empieza por un carácter de fórmula
            assert not texto.startswith(("=", "+", "-", "@", "\t", "\r"))


def test_inv043_xlsx_neutraliza_formulas_y_no_hay_celdas_de_formula(client):
    cat = client.post("/api/v1/categorias", json={"nombre": "=1+1", "icono": "", "tipo": "gasto"}, headers=A).json()
    for i, d in enumerate(PELIGROSAS):
        sembrar(descripcion=d, categoria_id=cat["id"], fecha=f"2026-11-{i + 1:02d}")
    r = pedir(client, desde="2026-11", formato="xlsx")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        hojas = [n for n in z.namelist() if n.startswith("xl/worksheets/")]
        for n in hojas:   # ni un solo elemento de fórmula en el XML
            assert not re.search(rb"<f[ >/]", z.read(n))
    hoja = hoja_xlsx(r)
    filas = list(hoja.iter_rows(min_row=2))
    assert len(filas) == len(PELIGROSAS)
    for fila, original in zip(filas, PELIGROSAS):
        categoria, descripcion = fila[2], fila[3]
        assert descripcion.data_type == "s" and categoria.data_type == "s"        # cadena explícita, nunca 'f'
        assert descripcion.quotePrefix is True and categoria.quotePrefix is True  # estilo quotePrefix
        assert descripcion.value == original and categoria.value == "=1+1"        # sin apóstrofo antepuesto
        assert not str(descripcion.value).startswith("'")
    assert all(c.data_type != "f" for fila in hoja.iter_rows() for c in fila)


def test_inv043_montos_y_fechas_no_se_prefijan(client):
    sembrar(fecha="2026-11-01", monto=0.5, descripcion="café")
    f = filas_csv(pedir(client, desde="2026-11"))[1]
    assert f[0] == "2026-11-01" and f[5] == "0,50"
    fila = next(hoja_xlsx(pedir(client, desde="2026-11", formato="xlsx")).iter_rows(min_row=2))
    assert fila[0].data_type == "d" and fila[0].quotePrefix is False
    assert fila[5].data_type == "n" and fila[5].value == 0.5 and fila[5].quotePrefix is False


def test_inv043_texto_normal_no_se_modifica(client):
    sembrar(descripcion="Almuerzo - menú del día")
    assert filas_csv(pedir(client, desde="2026-11"))[1][3] == "Almuerzo - menú del día"
    celda = next(hoja_xlsx(pedir(client, desde="2026-11", formato="xlsx")).iter_rows(min_row=2))[3]
    assert celda.value == "Almuerzo - menú del día" and celda.quotePrefix is False


# ── INV-044: límites ──────────────────────────────────────────────────────────

def test_inv044_rango_mayor_de_12_meses_responde_422(client):
    r = pedir(client, desde="2025-01", hasta="2026-02")
    assert r.status_code == 422 and r.json()["detail"] == "Puedes exportar hasta 12 meses por archivo"
    assert pedir(client, desde="2025-01", hasta="2026-01").status_code == 422     # 13 meses
    ok = pedir(client, desde="2025-03", hasta="2026-02")                           # 12 meses exactos
    assert ok.status_code == 200
    assert ok.headers["content-disposition"] == 'attachment; filename="finanzy-transacciones-2025-03_a_2026-02.csv"'
    assert pedir(client, desde="2027-01").status_code == 200                       # meses futuros: solo encabezados


def test_inv044_mas_de_10000_filas_responde_422_sin_truncar(client):
    sembrar(cantidad=10_001, descripcion="x")
    for formato in ("csv", "xlsx"):
        r = pedir(client, desde="2026-11", formato=formato)
        assert r.status_code == 422
        assert r.json() == {"detail": "Hay más de 10 000 transacciones en ese rango. Elige menos meses.",
                            "codigo": "exportacion_demasiadas_filas"}
        assert "content-disposition" not in r.headers
    demo_db.DemoTransaccionDB._transacciones.pop(next(iter(demo_db.DemoTransaccionDB._transacciones)))
    r = pedir(client, desde="2026-11")   # exactamente 10 000 de tamaño normal
    assert r.status_code == 200 and len(filas_csv(r)) == 10_001


def test_inv044_mas_de_4mb_responde_422_exportacion_demasiado_grande(client):
    sembrar_peor_caso(cantidad=6_000)
    for formato in ("csv", "xlsx"):
        r = pedir(client, desde="2026-11", formato=formato)
        assert r.status_code == 422, formato
        assert r.json() == {"detail": "El archivo superaría los 4 MB. Elige menos meses.", "codigo": DEMASIADO_GRANDE}
        assert "content-disposition" not in r.headers


def test_inv044_el_tope_de_bytes_corta_la_generacion_sin_acumular_todo(client, monkeypatch):
    paginas = []
    rng = random.Random(1)
    grande = "ñ" * 250   # ~500 bytes de descripción por fila

    def fake(usuario_id, desde, hasta, inicio, cantidad):
        paginas.append(inicio)
        return [{"fecha": "2026-11-01", "tipo": "gasto", "categoria_id": None, "descripcion": grande + str(rng.random()),
                 "medio_pago": None, "monto": 1, "whatsapp": False} for _ in range(cantidad)]

    monkeypatch.setattr(TransaccionDB, "pagina_para_exportar", staticmethod(fake))
    r = pedir(client, desde="2026-11")
    assert r.status_code == 422 and r.json()["codigo"] == DEMASIADO_GRANDE
    assert len(paginas) <= 9          # ~4 MB / ~0,5 MB por página: deja de pedir páginas (el total posible era 10)
    assert paginas == list(range(0, 1000 * len(paginas), 1000))


def test_inv044_pagina_todas_las_filas_mas_alla_de_1000(client, monkeypatch):
    sembrar(cantidad=2_500, descripcion="a")
    for n, t in enumerate(demo_db.DemoTransaccionDB._transacciones.values()):
        t["descripcion"] = f"fila {n:05d}"
    pedidos = []
    original = TransaccionDB.pagina_para_exportar

    def maximo_1000(usuario_id, desde, hasta, inicio, cantidad):   # como PostgREST: nunca más de 1000 por consulta
        pedidos.append((inicio, cantidad))
        return original(usuario_id, desde, hasta, inicio, min(cantidad, 1000))

    monkeypatch.setattr(TransaccionDB, "pagina_para_exportar", staticmethod(maximo_1000))
    r = pedir(client, desde="2026-11")
    descripciones = [f[3] for f in filas_csv(r)[1:]]
    assert len(descripciones) == 2_500 and len(set(descripciones)) == 2_500
    assert pedidos == [(0, 1000), (1000, 1000), (2000, 1000)]


@pytest.mark.parametrize("params", [
    {"desde": "2026-13"}, {"desde": "2026-1"}, {"desde": "2026-11\n"}, {"desde": "abc"}, {},
    {"desde": "2026-11", "hasta": "2026-00"}, {"desde": "2026-11", "hasta": "2026-10"},
    {"desde": "2026-11", "formato": "pdf"}, {"desde": "2026-11", "formato": "CSV"},
    {"desde": "0000-01"}, {"desde": "1999-12"}, {"desde": "2101-01"}, {"desde": "9999-12"},
    {"desde": "2026-11", "hasta": "9999-12"}, {"desde": "2099-12", "hasta": "2101-01"},
])
def test_inv044_parametros_invalidos_responden_422(client, monkeypatch, params):
    def no_debe_consultar(*a, **k):
        raise AssertionError("no se debe consultar la BD con parámetros inválidos")

    monkeypatch.setattr(TransaccionDB, "pagina_para_exportar", staticmethod(no_debe_consultar))
    r = pedir(client, **params)
    assert r.status_code == 422
    assert r.json()["detail"] in (
        "Formato de mes inválido (YYYY-MM)", "El mes inicial no puede ser posterior al final",
        "Formato no válido: usa csv o xlsx")


def test_inv044_error_de_la_bd_responde_503_sin_archivo_parcial(client, monkeypatch):
    llamadas = []

    def falla_en_la_segunda(usuario_id, desde, hasta, inicio, cantidad):
        llamadas.append(inicio)
        if inicio == 0:
            return [{"fecha": "2026-11-01", "tipo": "gasto", "categoria_id": None, "descripcion": "a", "medio_pago": None,
                     "monto": 1, "whatsapp": False}] * cantidad
        raise RuntimeError("clave-interna-de-la-bd")

    monkeypatch.setattr(TransaccionDB, "pagina_para_exportar", staticmethod(falla_en_la_segunda))
    for formato in ("csv", "xlsx"):
        r = pedir(client, desde="2026-11", formato=formato)
        assert r.status_code == 503
        assert r.json()["detail"] == "Servicio no disponible. Intenta de nuevo en unos minutos."
        assert "clave-interna" not in r.text and "content-disposition" not in r.headers
    assert llamadas == [0, 1000, 0, 1000]


def test_inv044_plazo_total_de_8s_responde_503_sin_archivo_parcial(client, monkeypatch):
    # El plazo real es de 8 s (se comprueba su valor); en la prueba se reduce para no esperar: la lógica es la misma.
    assert generador.PLAZO_SEGUNDOS == 8.0
    monkeypatch.setattr(generador, "PLAZO_SEGUNDOS", 0.5)
    pedidas = []

    def lenta(usuario_id, desde, hasta, inicio, cantidad):
        pedidas.append(inicio)
        time.sleep(0.3)
        return [{"fecha": "2026-11-01", "tipo": "gasto", "categoria_id": None, "descripcion": "a", "medio_pago": None,
                 "monto": 1, "whatsapp": False}] * cantidad

    monkeypatch.setattr(TransaccionDB, "pagina_para_exportar", staticmethod(lenta))
    t0 = time.monotonic()
    r = pedir(client, desde="2026-11")
    assert time.monotonic() - t0 < 1.5
    assert r.status_code == 503 and r.json()["detail"] == "La exportación tardó demasiado. Elige menos meses."
    assert "content-disposition" not in r.headers
    time.sleep(0.8)   # el hilo se detiene solo: no sigue pidiendo páginas
    assert len(pedidas) <= 3


def test_inv044_limite_de_10_descargas_por_minuto_responde_429(client):
    for _ in range(10):
        assert pedir(client, A, desde="2026-11").status_code == 200
    r = pedir(client, A, desde="2026-11")
    assert r.status_code == 429 and r.json()["detail"] == "Demasiadas descargas. Espera un momento e intenta de nuevo."
    assert pedir(client, B, desde="2026-11").status_code == 200   # otro usuario no se ve afectado


# ── INV-045: fidelidad del archivo ────────────────────────────────────────────

def test_inv045_csv_utf8_con_bom_separador_punto_y_coma_y_columnas(client):
    cat = client.post("/api/v1/categorias", json={"nombre": "Mercado", "icono": "", "tipo": "gasto"}, headers=A).json()
    sembrar(fecha="2026-11-20", descripcion="tercera", categoria_id=cat["id"], monto=1234.5, medio_pago="debito")
    sembrar(fecha="2026-11-02", descripcion="primera; con punto y coma", monto=10, tipo="ingreso")
    sembrar(fecha="2026-11-09", descripcion='con "comillas"', monto=20)
    sembrar(fecha="2026-10-30", descripcion="del mes anterior")
    r = pedir(client, desde="2026-11")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert r.headers["content-disposition"] == 'attachment; filename="finanzy-transacciones-2026-11.csv"'
    assert r.content.startswith(b"\xef\xbb\xbf") and b"\r\n" in r.content
    # texto SIEMPRE entre comillas (H4); el monto, sin comillas y con coma decimal
    assert r.content.decode("utf-8-sig").split("\r\n")[0] == ";".join(f'"{e}"' for e in ENCABEZADOS)
    assert '"tercera";"Débito";1234,50;"App";""\r\n' in r.content.decode("utf-8-sig")
    filas = filas_csv(r)
    assert filas[0] == ENCABEZADOS
    assert [f[3] for f in filas[1:]] == ["primera; con punto y coma", 'con "comillas"', "tercera"]  # fecha ascendente
    assert filas[3] == ["2026-11-20", "Gasto", "Mercado", "tercera", "Débito", "1234,50", "App", ""]
    assert filas[1][1] == "Ingreso" and filas[1][5] == "10,00"


def test_inv045_xlsx_se_abre_con_openpyxl_y_tiene_hoja_transacciones(client):
    for mes, dia in (("2026-09", 15), ("2026-10", 3), ("2026-11", 28), ("2026-08", 1), ("2026-12", 1)):
        sembrar(fecha=f"{mes}-{dia:02d}", descripcion=f"de {mes}", monto=100.25)
    r = pedir(client, desde="2026-09", hasta="2026-11", formato="xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert r.headers["content-disposition"] == 'attachment; filename="finanzy-transacciones-2026-09_a_2026-11.xlsx"'
    libro = load_workbook(io.BytesIO(r.content))
    assert libro.sheetnames == ["Transacciones"]
    filas = list(libro["Transacciones"].iter_rows(values_only=True))
    assert list(filas[0]) == ENCABEZADOS
    assert [f[3] for f in filas[1:]] == ["de 2026-09", "de 2026-10", "de 2026-11"]
    assert filas[1][0] == datetime(2026, 9, 15) and filas[1][5] == 100.25
    celdas = list(libro["Transacciones"].iter_rows(min_row=2, max_row=2))[0]
    assert celdas[0].data_type == "d" and celdas[0].number_format == "yyyy-mm-dd"
    assert celdas[5].data_type == "n" and celdas[5].number_format == "#,##0.00"


def test_inv045_montos_en_cop_tal_como_se_guardan(client, users):
    users["usd@example.com"] = {"id": "id-usd", "email": "usd@example.com", "is_active": True,
                                "currency": "USD", "session_version": 0}   # moneda de visualización: no cambia el archivo
    usd = auth_header("id-usd")
    sembrar("id-usd", monto=42000.50, descripcion="m")
    assert filas_csv(pedir(client, usd, desde="2026-11"))[1][5] == "42000,50"
    assert next(hoja_xlsx(pedir(client, usd, desde="2026-11", formato="xlsx")).iter_rows(min_row=2))[5].value == 42000.5


def test_inv045_sin_filas_exporta_solo_encabezados(client):
    r = pedir(client, desde="2026-11")
    assert r.status_code == 200 and filas_csv(r) == [ENCABEZADOS]
    x = pedir(client, desde="2026-11", formato="xlsx")
    assert [list(f) for f in hoja_xlsx(x).iter_rows(values_only=True)] == [ENCABEZADOS]


def test_inv045_origen_whatsapp_y_app_y_medio_de_pago_en_espanol(client):
    por_whatsapp = sembrar(descripcion="por whatsapp", medio_pago="debito", fecha="2026-11-01")[0]
    sembrar(descripcion="por la app", fecha="2026-11-02")
    ajena = sembrar("user-b", descripcion="de B por whatsapp")[0]
    for tid, usuario in ((por_whatsapp, "user-a"), (ajena, "user-b")):
        whatsapp_db._Memoria.registros.append({"transaccion_id": tid, "usuario_id": usuario, "lote": "w1",
                                               "creado_en": datetime.now(timezone.utc)})
    filas = filas_csv(pedir(client, desde="2026-11"))
    assert filas[1][3:] == ["por whatsapp", "Débito", "10,00", "WhatsApp", ""]
    assert filas[2][3:] == ["por la app", "", "10,00", "App", ""]
    medios = {"debito": "Débito", "credito": "Crédito", "efectivo": "Efectivo", "transferencia": "Transferencia",
              "nequi_daviplata": "Nequi / Daviplata"}
    for i, codigo in enumerate(medios):
        sembrar(descripcion=f"m-{codigo}", medio_pago=codigo, fecha=f"2026-12-{i + 1:02d}")
    f = {x[3]: x[4] for x in filas_csv(pedir(client, desde="2026-12"))[1:]}
    assert f == {f"m-{c}": n for c, n in medios.items()}


def test_inv045_origen_solo_app_o_whatsapp_las_recurrentes_y_abonos_salen_como_app(client):
    rec = client.post("/api/v1/recurrentes", json={
        "tipo": "gasto", "monto": 1500, "descripcion": "Arriendo", "frecuencia": "mensual",
        "proxima_fecha": "2026-11-05", "medio_pago": "transferencia"}, headers=A).json()
    assert client.post(f"/api/v1/recurrentes/{rec['id']}/confirmar", json={"ocurrencia": "2026-11-05"}, headers=A).status_code == 200
    meta = client.post("/api/v1/metas", json={"nombre": "Viaje", "monto_objetivo": 1000, "fecha_objetivo": "2027-01-01"}, headers=A).json()
    assert client.post(f"/api/v1/metas/{meta['id']}/abonar", json={"monto": 50, "fecha": "2026-11-22"}, headers=A).status_code == 200
    filas = filas_csv(pedir(client, desde="2026-11"))[1:]
    assert len(filas) == 2 and {f[6] for f in filas} == {"App"}


# ── REQ-N-020: tamaño ─────────────────────────────────────────────────────────

def test_req_n020_peor_caso_real_con_comillas_multibyte_y_cuenta_responde_422(client):
    # La columna «Cuenta» (CHG-019) aún no existe: aquí el peor caso es el de las 7 columnas actuales
    sembrar_peor_caso(10_000)
    for formato in ("csv", "xlsx"):
        r = pedir(client, desde="2026-11", formato=formato)
        assert r.status_code == 422, formato
        assert r.json()["codigo"] == DEMASIADO_GRANDE
        assert len(r.content) < 1000     # no se entrega el archivo, solo el error


def test_req_n020_descripciones_ascii_de_255_caracteres_caben_en_4mb(client):
    rng = random.Random(3)
    letras = "abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    for i in range(10_000):
        sembrar(fecha=f"2026-11-{1 + i % 28:02d}", descripcion=texto_aleatorio(rng, 255, letras))
    csv_ = pedir(client, desde="2026-11")
    assert csv_.status_code == 200 and len(csv_.content) < 4_000_000 and len(filas_csv(csv_)) == 10_001
    xlsx = pedir(client, desde="2026-11", formato="xlsx")
    assert xlsx.status_code == 200 and len(xlsx.content) < 4_000_000
    assert hoja_xlsx(xlsx).max_row == 10_001


@pytest.mark.parametrize("cantidad, largo, alfabeto, formato", [
    (50, 5, "ab", "csv"), (50, 5, "ab", "xlsx"),
    (4_000, 255, "abcdefghijklmnopqrstuvwxyz", "csv"), (4_000, 255, "abcdefghijklmnopqrstuvwxyz", "xlsx"),
    (6_000, 250, "".join(CJK[:5000]), "csv"), (6_000, 250, "".join(CJK), "xlsx"),
    (9_000, 255, "ñ😀\"", "csv"),
])
def test_req_n020_ningun_archivo_entregado_supera_4_000_000_bytes(client, cantidad, largo, alfabeto, formato):
    rng = random.Random(cantidad + largo)
    for i in range(cantidad):
        sembrar(fecha=f"2026-11-{1 + i % 28:02d}", descripcion=texto_aleatorio(rng, largo, alfabeto))
    r = pedir(client, desde="2026-11", formato=formato)
    if r.status_code == 200:
        assert len(r.content) <= 4_000_000
    else:
        assert r.status_code == 422 and r.json()["codigo"] == DEMASIADO_GRANDE and len(r.content) < 1000


# ── REQ-N-019 y REQ-N-026: rendimiento ────────────────────────────────────────

def test_req_n019_10000_filas_en_menos_de_3s_csv_y_6s_xlsx(client):
    cat = client.post("/api/v1/categorias", json={"nombre": "Mercado", "icono": "", "tipo": "gasto"}, headers=A).json()
    sembrar(cantidad=10_000, descripcion="Almuerzo de prueba", categoria_id=cat["id"], medio_pago="credito", monto=15000.75)
    t0 = time.monotonic()
    assert pedir(client, desde="2026-11").status_code == 200
    assert time.monotonic() - t0 < 3
    t0 = time.monotonic()
    r = pedir(client, desde="2026-11", formato="xlsx")
    assert r.status_code == 200 and time.monotonic() - t0 < 6


def test_req_n026_la_generacion_no_bloquea_el_bucle_de_eventos():
    sembrar(cantidad=10_000, descripcion="Almuerzo de prueba", medio_pago="credito", monto=15000.75)

    async def escenario():
        mayor_pausa, activo = 0.0, True

        async def latido():   # si el bucle se bloquea, la pausa entre latidos crece
            nonlocal mayor_pausa
            previo = time.monotonic()
            while activo:
                await asyncio.sleep(0.01)
                ahora = time.monotonic()
                mayor_pausa = max(mayor_pausa, ahora - previo)
                previo = ahora

        tarea = asyncio.create_task(latido())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://prueba") as c:
            respuesta = await c.get(URL, params={"desde": "2026-11", "formato": "xlsx"}, headers=A)
            activo = False
            await tarea
        return respuesta, mayor_pausa

    respuesta, mayor_pausa = asyncio.run(escenario())
    assert respuesta.status_code == 200
    assert mayor_pausa < 0.5


# ── Ciclo 2 (CHG-018): H1 rama Supabase con cliente FALSO ─────────────────────

class _Consulta:
    """Registra la cadena de llamadas de PostgREST y responde con las filas que dicte `fuente(tabla, llamadas)`."""

    def __init__(self, cliente, tabla):
        self.cliente, self.tabla, self.llamadas = cliente, tabla, []

    def __getattr__(self, nombre):
        def registrar(*args, **kwargs):
            self.llamadas.append((nombre, args))
            return self
        return registrar

    def execute(self):
        self.cliente.consultas.append(self)
        filas = self.cliente.fuente(self)
        return type("R", (), {"data": filas})()

    def valor(self, nombre):
        return [a for n, a in self.llamadas if n == nombre]


class _ClienteFalso:
    def __init__(self, fuente):
        self.fuente, self.consultas = fuente, []

    def table(self, nombre):
        return _Consulta(self, nombre)


def _con_supabase_falso(monkeypatch, fuente):
    from app.models import plataapp
    cliente = _ClienteFalso(fuente)
    monkeypatch.setattr(plataapp, "_supabase_ok", lambda: True)
    monkeypatch.setattr(plataapp.auth_estado, "cliente_estado", lambda: cliente)   # CHG-026: cliente con plazo
    return cliente


def _fila_bd(n, embed=None):
    return {"fecha": "2026-11-01", "tipo": "gasto", "categoria_id": None, "descripcion": f"fila {n:05d}",
            "medio_pago": None, "monto": 1, "whatsapp_registros": embed}


def test_h1_supabase_consulta_con_usuario_de_la_sesion_orden_y_rango(client, monkeypatch):
    cliente = _con_supabase_falso(monkeypatch, lambda q: [])
    r = pedir(client, A, desde="2026-10", hasta="2026-11", formato="csv")
    assert r.status_code == 200
    tx = [q for q in cliente.consultas if q.tabla == "transacciones"]
    cat = [q for q in cliente.consultas if q.tabla == "categorias"]
    assert len(tx) == 1 and len(cat) == 1
    q = tx[0]
    assert q.valor("eq") == [("usuario_id", "user-a")]            # el dueño sale de la sesión (INV-042)
    assert q.valor("gte") == [("fecha", "2026-10-01")] and q.valor("lt") == [("fecha", "2026-12-01")]
    assert [a for a in q.valor("order")] == [("fecha",), ("id",)]   # la tabla no tiene created_at
    assert q.valor("range") == [(0, 999)]
    assert "whatsapp_registros(transaccion_id)" in q.valor("select")[0][0]
    assert cat[0].valor("eq") == [("usuario_id", "user-a")]
    # otro usuario: su propio id, nunca el de A
    cliente.consultas.clear()
    pedir(client, B, desde="2026-11")
    assert all(q.valor("eq") == [("usuario_id", "user-b")] for q in cliente.consultas)


def test_h1_supabase_pagina_1000_exactas_y_luego_menos_sin_saltar_ni_duplicar(client, monkeypatch):
    total = 1500
    filas = [_fila_bd(n) for n in range(total)]

    def fuente(q):
        if q.tabla != "transacciones":
            return []
        a, b = q.valor("range")[0]
        return filas[a:b + 1]

    cliente = _con_supabase_falso(monkeypatch, fuente)
    r = pedir(client, A, desde="2026-11")
    descripciones = [f[3] for f in filas_csv(r)[1:]]
    assert descripciones == [f"fila {n:05d}" for n in range(total)]       # ni saltos ni duplicados
    rangos = [q.valor("range")[0] for q in cliente.consultas if q.tabla == "transacciones"]
    assert rangos == [(0, 999), (1000, 1999)]


def test_h1_supabase_pagina_exacta_de_1000_pide_otra_vacia_y_termina(client, monkeypatch):
    filas = [_fila_bd(n) for n in range(1000)]
    cliente = _con_supabase_falso(
        monkeypatch, lambda q: filas[q.valor("range")[0][0]:q.valor("range")[0][1] + 1] if q.tabla == "transacciones" else [])
    r = pedir(client, A, desde="2026-11")
    assert len(filas_csv(r)) == 1001
    assert [q.valor("range")[0] for q in cliente.consultas if q.tabla == "transacciones"] == [(0, 999), (1000, 1999)]


@pytest.mark.parametrize("embed,origen", [
    ({"transaccion_id": "t1"}, "WhatsApp"),     # relación uno a uno: objeto
    ([{"transaccion_id": "t1"}], "WhatsApp"),   # lista con un registro
    (None, "App"),
    ([], "App"),
])
def test_h1_supabase_embed_de_whatsapp_registros_define_el_origen(client, monkeypatch, embed, origen):
    _con_supabase_falso(monkeypatch, lambda q: [_fila_bd(1, embed)] if q.tabla == "transacciones" else [])
    for formato in ("csv", "xlsx"):
        r = pedir(client, A, desde="2026-11", formato=formato)
        assert r.status_code == 200
        fila = filas_csv(r)[1] if formato == "csv" else [c.value for c in list(hoja_xlsx(r).iter_rows())[1]]
        assert fila[6] == origen


def test_h1_supabase_categorias_paginadas_solo_las_del_usuario(client, monkeypatch):
    todas = [{"id": f"c{n:05d}", "nombre": f"Cat {n}"} for n in range(1200)]

    def fuente(q):
        if q.tabla == "categorias":
            a, b = q.valor("range")[0]
            return todas[a:b + 1]
        return [dict(_fila_bd(1), categoria_id="c01150")]

    cliente = _con_supabase_falso(monkeypatch, fuente)
    r = pedir(client, A, desde="2026-11")
    assert filas_csv(r)[1][2] == "Cat 1150"          # la categoría está en la 2.ª página
    cats = [q for q in cliente.consultas if q.tabla == "categorias"]
    assert [q.valor("range")[0] for q in cats] == [(0, 999), (1000, 1999)]
    assert all(q.valor("eq") == [("usuario_id", "user-a")] for q in cats)


def test_h1_modo_memoria_ordena_por_fecha_y_conserva_el_orden_de_insercion():
    sembrar(fecha="2026-11-05", descripcion="tarde")
    sembrar(fecha="2026-11-05", descripcion="temprano")
    sembrar(fecha="2026-11-01", descripcion="primero")
    filas = TransaccionDB.pagina_para_exportar("user-a", "2026-11", "2026-11", 0, 1000)
    assert [f["descripcion"] for f in filas] == ["primero", "tarde", "temprano"]


def test_h1_la_consulta_de_supabase_no_usa_columnas_inexistentes_en_transacciones(client, monkeypatch):
    """La tabla `transacciones` de producción NO tiene `created_at` (error real: APIError → 503 en producción).
    Columnas reales: id, usuario_id, categoria_id, monto, descripcion, fecha, tipo, medio_pago."""
    reales = {"id", "usuario_id", "categoria_id", "monto", "descripcion", "fecha", "tipo", "medio_pago"}
    cliente = _con_supabase_falso(monkeypatch, lambda q: [])
    assert pedir(client, A, desde="2026-11", hasta="2026-11", formato="csv").status_code == 200
    q = [x for x in cliente.consultas if x.tabla == "transacciones"][0]
    usadas = ({a[0] for a in q.valor("order")} | {a[0] for a in q.valor("eq")}
              | {a[0] for a in q.valor("gte")} | {a[0] for a in q.valor("lt")})
    assert usadas <= reales, usadas - reales


# ── Ciclo 2: H2 tope de exportaciones simultáneas ─────────────────────────────

def test_h2_ejecutor_lleno_responde_503_inmediato_sin_encolar_y_la_ranura_se_libera(client, monkeypatch):
    sembrar(descripcion="x")
    llegaron, soltar = threading.Event(), threading.Event()
    leidas = []

    def bloqueada(usuario_id, desde, hasta, inicio, cantidad):
        leidas.append(inicio)
        llegaron.set()
        soltar.wait(5)
        return []

    monkeypatch.setattr(TransaccionDB, "pagina_para_exportar", staticmethod(bloqueada))
    # el plazo grande evita que venza antes de comprobar el rechazo
    monkeypatch.setattr(generador, "PLAZO_SEGUNDOS", 5.0)
    for _ in range(exportar_routes.MAX_EXPORTACIONES_SIMULTANEAS):
        assert exportar_routes._ranuras.acquire(blocking=False)
    try:
        t0 = time.monotonic()
        r = pedir(client, A, desde="2026-11")
        assert time.monotonic() - t0 < 0.5                       # inmediato
        assert r.status_code == 503 and r.json()["detail"] == "Servicio no disponible. Intenta de nuevo en unos minutos."
        assert r.headers["cache-control"] == "no-store" and "content-disposition" not in r.headers
        assert leidas == []                                      # no se encoló ni empezó trabajo
    finally:
        for _ in range(exportar_routes.MAX_EXPORTACIONES_SIMULTANEAS):
            exportar_routes._ranuras.release()
    soltar.set()
    # la ranura vuelve tras terminar el hilo: dos exportaciones seguidas funcionan
    monkeypatch.undo()
    for _ in range(3):
        assert pedir(client, A, desde="2026-11").status_code == 200
    assert exportar_routes._ranuras._value == exportar_routes.MAX_EXPORTACIONES_SIMULTANEAS


def test_h2_dos_en_curso_la_tercera_recibe_503_y_health_responde(client, monkeypatch):
    llegaron = threading.Semaphore(0)
    soltar = threading.Event()

    def bloqueada(usuario_id, desde, hasta, inicio, cantidad):
        llegaron.release()
        soltar.wait(10)
        return []

    monkeypatch.setattr(TransaccionDB, "pagina_para_exportar", staticmethod(bloqueada))
    monkeypatch.setattr(generador, "PLAZO_SEGUNDOS", 10.0)

    async def escenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://prueba") as c:
            # una exportación en curso por usuario: las dos primeras son de usuarios distintos
            tareas = [asyncio.create_task(c.get(URL, params={"desde": "2026-11"}, headers=h)) for h in (A, B)]
            limite = time.monotonic() + 5     # tiempo acotado: la prueba nunca debe colgarse
            for _ in range(2):
                while not llegaron.acquire(blocking=False):
                    assert time.monotonic() < limite
                    await asyncio.sleep(0.01)
            tercera = await c.get(URL, params={"desde": "2026-11"}, headers=auth_header("user-c"))
            salud = await c.get("/health")
            soltar.set()
            return tercera, salud, await asyncio.gather(*tareas)

    tercera, salud, primeras = asyncio.run(escenario())
    assert tercera.status_code == 503
    assert salud.status_code == 200 and salud.json() == {"status": "healthy"}
    assert [p.status_code for p in primeras] == [200, 200]
    time.sleep(0.2)
    assert exportar_routes._ranuras._value == exportar_routes.MAX_EXPORTACIONES_SIMULTANEAS


def test_h2_tras_el_plazo_la_ranura_se_libera_cuando_el_hilo_termina(client, monkeypatch):
    monkeypatch.setattr(generador, "PLAZO_SEGUNDOS", 0.3)

    def lenta(usuario_id, desde, hasta, inicio, cantidad):
        time.sleep(0.5)
        return [_fila_bd(0)] * cantidad

    monkeypatch.setattr(TransaccionDB, "pagina_para_exportar", staticmethod(lenta))
    assert pedir(client, A, desde="2026-11").status_code == 503
    time.sleep(1.0)    # el hilo ve el plazo/`detener` tras la página en curso y termina
    assert exportar_routes._ranuras._value == exportar_routes.MAX_EXPORTACIONES_SIMULTANEAS


def test_h2_el_xlsx_comprueba_detener_cada_500_filas_al_escribir():
    class Evento:
        """Falso `threading.Event`: pide parar tras N consultas (la lectura de 2500 filas consulta 6 veces)."""
        def __init__(self, tras):
            self.tras, self.consultas = tras, 0

        def is_set(self):
            self.consultas += 1
            return self.consultas > self.tras

    filas = [_fila_bd(n) | {"whatsapp": False} for n in range(2500)]
    leer = lambda inicio, cantidad: filas[inicio:inicio + cantidad]
    ev = Evento(tras=8)
    with pytest.raises(generador.ExportacionLenta):
        generador.generar_archivo("xlsx", leer, {}, ev, 60)
    assert ev.consultas == 9        # 6 de la lectura + comprobaciones en las filas 0, 500 y 1000 de la escritura


# ── Ciclo 3: una exportación por usuario, desconexión y limpieza ──────────────

def test_c3_una_sola_exportacion_en_curso_por_usuario_y_otro_usuario_no_se_ve_afectado(client, monkeypatch):
    llegaron = threading.Semaphore(0)
    soltar = threading.Event()

    def bloqueada(usuario_id, desde, hasta, inicio, cantidad):
        llegaron.release()
        soltar.wait(10)
        return []

    monkeypatch.setattr(TransaccionDB, "pagina_para_exportar", staticmethod(bloqueada))
    monkeypatch.setattr(generador, "PLAZO_SEGUNDOS", 10.0)

    async def escenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://prueba") as c:
            limite = time.monotonic() + 5     # tiempo acotado: la prueba nunca debe colgarse
            primera = asyncio.create_task(c.get(URL, params={"desde": "2026-11"}, headers=A))
            while not llegaron.acquire(blocking=False):
                assert time.monotonic() < limite
                await asyncio.sleep(0.01)
            t0 = time.monotonic()
            segunda = await c.get(URL, params={"desde": "2026-11"}, headers=A)
            rapido = time.monotonic() - t0 < 0.5
            de_otro = asyncio.create_task(c.get(URL, params={"desde": "2026-11"}, headers=B))
            while not llegaron.acquire(blocking=False):
                assert time.monotonic() < limite
                await asyncio.sleep(0.01)
            soltar.set()
            return segunda, rapido, await primera, await de_otro

    segunda, rapido, primera, de_otro = asyncio.run(escenario())
    assert segunda.status_code == 429 and rapido
    assert segunda.json()["detail"] == "Ya tienes una exportación en curso. Espera a que termine."
    assert segunda.headers["cache-control"] == "no-store" and "content-disposition" not in segunda.headers
    assert primera.status_code == 200 and de_otro.status_code == 200
    time.sleep(0.2)
    assert exportar_routes._en_curso == set()
    assert exportar_routes._ranuras._value == exportar_routes.MAX_EXPORTACIONES_SIMULTANEAS


def test_c3_el_usuario_se_libera_tras_terminar_o_fallar_y_si_el_ejecutor_esta_lleno(client, monkeypatch):
    assert pedir(client, A, desde="2026-11").status_code == 200
    assert exportar_routes._en_curso == set()

    def falla(*a):
        raise RuntimeError("BD caída")

    original = TransaccionDB.pagina_para_exportar
    monkeypatch.setattr(TransaccionDB, "pagina_para_exportar", staticmethod(falla))
    assert pedir(client, A, desde="2026-11").status_code == 503
    time.sleep(0.2)
    assert exportar_routes._en_curso == set()
    monkeypatch.setattr(TransaccionDB, "pagina_para_exportar", original)
    assert pedir(client, A, desde="2026-11").status_code == 200
    # ejecutor lleno: el 503 tampoco deja al usuario bloqueado
    for _ in range(exportar_routes.MAX_EXPORTACIONES_SIMULTANEAS):
        assert exportar_routes._ranuras.acquire(blocking=False)
    try:
        assert pedir(client, A, desde="2026-11").status_code == 503
        assert exportar_routes._en_curso == set()
    finally:
        for _ in range(exportar_routes.MAX_EXPORTACIONES_SIMULTANEAS):
            exportar_routes._ranuras.release()
    assert pedir(client, A, desde="2026-11").status_code == 200


def test_c3_la_desconexion_del_cliente_detiene_el_hilo_y_libera_ranura_y_usuario(monkeypatch):
    llegaron, soltar = threading.Event(), threading.Event()
    leidas = []

    def bloqueada(usuario_id, desde, hasta, inicio, cantidad):
        leidas.append(inicio)
        llegaron.set()
        soltar.wait(5)
        return [_fila_bd(n) | {"whatsapp": False} for n in range(cantidad)]    # página llena: pediría otra

    monkeypatch.setattr(TransaccionDB, "pagina_para_exportar", staticmethod(bloqueada))
    monkeypatch.setattr(generador, "PLAZO_SEGUNDOS", 10.0)

    async def escenario():
        tarea = asyncio.create_task(exportar_routes.exportar_transacciones("2026-11", None, None, A["Authorization"]))
        while not llegaron.is_set():
            await asyncio.sleep(0.01)
        tarea.cancel()                      # el cliente se desconecta
        with pytest.raises(asyncio.CancelledError):
            await tarea
        soltar.set()
        await asyncio.sleep(0.5)

    asyncio.run(escenario())
    assert leidas == [0]                    # el hilo vio `detener` y no pidió la 2.ª página
    assert exportar_routes._ranuras._value == exportar_routes.MAX_EXPORTACIONES_SIMULTANEAS
    assert exportar_routes._en_curso == set()


def test_c3_un_fallo_al_borrar_tras_guardar_no_convierte_el_archivo_en_error(monkeypatch, tmp_path):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    filas = [_fila_bd(n) | {"whatsapp": False} for n in range(5)]
    leer = lambda inicio, cantidad: filas[inicio:inicio + cantidad]
    borrados = []

    def unlink_falla(ruta):
        borrados.append(ruta)
        raise OSError("no se pudo borrar")

    monkeypatch.setattr(generador.os, "unlink", unlink_falla)
    assert generador.generar_archivo("xlsx", leer, {}, None, 60).startswith(b"PK")
    assert len(borrados) == 1


def test_c3_limpiar_libro_tras_guardar_no_toca_las_hojas_y_un_oserror_no_propaga(monkeypatch):
    class Hoja:
        _writer = type("E", (), {"out": "/tmp/no-debe-tocarse"})()

    class Libro:
        _sheets = [Hoja()]
        cerrado = False

        def close(self):
            self.cerrado = True

    quitados = []
    monkeypatch.setattr(generador.os, "remove", lambda ruta: quitados.append(ruta))
    libro = Libro()
    generador._limpiar_libro(libro, guardado=True)
    assert libro.cerrado and quitados == []
    # sin guardar sí se limpian las hojas, y un OSError al borrar no se propaga
    monkeypatch.setattr(generador.os, "remove", lambda ruta: (_ for _ in ()).throw(PermissionError("denegado")))
    generador._limpiar_libro(Libro(), guardado=False)


# ── Ciclo 2: H3 sin temporales ────────────────────────────────────────────────

def test_h3_el_corte_por_plazo_en_el_xlsx_no_deja_temporales(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    filas = [_fila_bd(n) | {"whatsapp": False} for n in range(1200)]
    leer = lambda inicio, cantidad: filas[inicio:inicio + cantidad]

    class ParaEnLaEscritura:
        def __init__(self):
            self.consultas = 0

        def is_set(self):
            self.consultas += 1
            return self.consultas > 4     # la lectura (2 páginas) consulta 4 veces: corta al escribir

    with pytest.raises(generador.ExportacionLenta):
        generador.generar_archivo("xlsx", leer, {}, ParaEnLaEscritura(), 60)
    assert list(tmp_path.iterdir()) == []
    # y un xlsx correcto tampoco deja nada
    assert generador.generar_archivo("xlsx", leer, {}, None, 60).startswith(b"PK")
    assert list(tmp_path.iterdir()) == []
    # ni uno que supera el tope de bytes
    monkeypatch.setattr(generador, "MAX_BYTES", 100)
    with pytest.raises(generador.ExportacionDemasiadoGrande):
        generador.generar_archivo("xlsx", leer, {}, None, 60)
    assert list(tmp_path.iterdir()) == []


# ── Ciclo 2: H4 CSV con todo el texto entre comillas ──────────────────────────

DESCRIPCIONES_CSV = ["x,=1+1", "x;=1+1", 'dijo "hola", =1+1', "línea 1\nlínea 2,=2+2", "=1+1,=2+2", "a\r\nb;c", ",=1", "normal",
                     'x,"=2+3', 'x,"=HYPERLINK(""http://e"";""a"")', 'x\n"=1', 'x,"-1', "a\n=1+1", "a\r\n=1+1",
                     "a\r\n-1", 'a,",",=1', "a\n\n=1"]


def test_h4_csv_todo_el_texto_va_entre_comillas_y_el_monto_no(client):
    for i, d in enumerate(DESCRIPCIONES_CSV):
        sembrar(descripcion=d, monto=1234.5, fecha=f"2026-11-{i + 1:02d}", medio_pago="debito")
    texto = pedir(client, desde="2026-11").content.decode("utf-8-sig")
    assert texto.startswith('"Fecha";"Tipo";"Categoría";"Descripción";"Medio de pago";"Monto (COP)";"Origen";"Cuenta"\r\n')
    assert '"2026-11-01";"Gasto";"Sin categoría";"x,\'=1+1";"Débito";1234,50;"App";""\r\n' in texto
    assert '"dijo ""hola"",\' =1+1"' in texto
    assert '"línea 1\nlínea 2,\'=2+2"' in texto
    assert ';"\'=1+1,\'=2+2";' in texto          # inicio y fragmento tras «,» neutralizados, ya entre comillas


def test_h4_csv_al_releer_con_punto_y_coma_los_valores_coinciden_y_las_comillas_protegen_comas_y_saltos(client):
    for i, d in enumerate(DESCRIPCIONES_CSV):
        sembrar(descripcion=d, monto=1234.5, fecha=f"2026-11-{i + 1:02d}")
    texto = pedir(client, desde="2026-11").content.decode("utf-8-sig")
    esperadas = [generador.neutralizar_csv(d) for d in DESCRIPCIONES_CSV]
    assert esperadas[:8] == ["x,'=1+1", "x;'=1+1", 'dijo "hola",\' =1+1', "línea 1\nlínea 2,'=2+2", "'=1+1,'=2+2",
                             "a\r\nb;c", ",'=1", "normal"]
    # con «;» (el separador del archivo) la lectura es exacta
    filas = list(csv.reader(io.StringIO(texto, newline=""), delimiter=";"))[1:]
    assert [f[3] for f in filas] == esperadas and all(len(f) == 8 and f[5] == "1234,50" for f in filas)
    for d in esperadas:
        assert '"' + d.replace('"', '""') + '"' in texto
    # Con CUALQUIER delimitador («;» o «,») ninguna celda resultante empieza por un carácter de fórmula
    for delimitador in (";", ","):
        celdas = [c for linea in csv.reader(io.StringIO(texto, newline=""), delimiter=delimitador) for c in linea]
        assert any(c.startswith("'") for c in celdas)
        for celda in celdas:
            assert not celda.startswith(("=", "+", "-", "@", "\t", "\r")), (delimitador, celda)


@pytest.mark.parametrize("texto, esperado", [
    ("x,=1+1", "x,'=1+1"), ("x;=1+1", "x;'=1+1"), ("a, =cmd", "a,' =cmd"), ("a,@SUM(1)", "a,'@SUM(1)"),
    ("a,-1", "a,'-1"), ("a,+1", "a,'+1"), ("a,\t=1", "a,'\t=1"), ("a,\r=1", "a,'\r'=1"),
    ("a,=1,-2; +3,@x", "a,'=1,'-2;' +3,'@x"), ("=1,=2", "'=1,'=2"), ("a,,=1", "a,,'=1"), ("a,   =1", "a,'   =1"),
    ("pan, leche, huevos", "pan, leche, huevos"), ("ida-vuelta, 3-4", "ida-vuelta, 3-4"), ("a=b, c+d", "a=b, c+d"),
    ("normal", "normal"), ("", ""), ("a,", "a,"), ("a, ", "a, "),
    # ciclo 3 (I-1): comillas y saltos de línea entre el separador y el carácter peligroso
    ('x,"=2+3', 'x,\'"=2+3'), ('x,"=HYPERLINK(""http://e"";""a"")', 'x,\'"=HYPERLINK(""http://e"";""a"")'),
    ('x\n"=1', 'x\n\'"=1'), ('x,"-1', 'x,\'"-1'), ("a\n=1+1", "a\n'=1+1"), ("a\r\n=1+1", "a\r\n'=1+1"),
    ("a\r\n-1", "a\r\n'-1"), ('x,"=1', 'x,\'"=1'), ("a\n\n\n=1", "a\n\n\n'=1"), ('a,",",=1', 'a,",",\'=1'),
    ('a,"" "=1', 'a,\'"" "=1'), ('a,"",""=1', 'a,"",\'""=1'), ("a\n=1;-2,\n@3", "a\n'=1;'-2,\n'@3"),
    ("a\nb", "a\nb"), ("a\n b", "a\n b"), ('dijo "hola", ok', 'dijo "hola", ok'),
])
def test_inv043_neutralizar_csv_fragmentos_tras_coma_o_punto_y_coma(texto, esperado):
    assert generador.neutralizar_csv(texto) == esperado


def test_inv043_propiedad_ninguna_celda_empieza_por_caracter_peligroso_con_ambos_delimitadores():
    """Cadenas aleatorias de caracteres de fórmula, separadores, comillas y letras: tras neutralizar y generar el CSV
    completo, ni con «,» ni con «;» queda una celda que empiece por = + - @ tab o CR."""
    rng = random.Random(43)
    alfabeto = list("=+-@\t\r\n,;\"") + list("ab ") * 2
    textos = [texto_aleatorio(rng, rng.randint(1, 14), alfabeto) for _ in range(3000)]
    for i in range(0, len(textos), 100):
        filas = [("2026-11-01", "Gasto", "Sin categoría", t, "Débito", generador._monto(1234.5), "App", "")   # la columna 8 «Cuenta» se prueba aparte (test_cuentas_integracion.py)
                 for t in textos[i:i + 100]]
        csv_bytes = generador._generar_csv(iter([filas]))
        texto = csv_bytes.decode("utf-8-sig")
        for delimitador in (",", ";"):
            for linea in csv.reader(io.StringIO(texto, newline=""), delimiter=delimitador):
                for celda in linea:
                    assert not celda.startswith(("=", "+", "-", "@", "\t", "\r")), (delimitador, celda, textos[i:i + 100])
        # con «;» (el del archivo) la lectura es exacta: fechas y montos intactos
        leidas = list(csv.reader(io.StringIO(texto, newline=""), delimiter=";"))[1:]
        assert all(f[0] == "2026-11-01" and f[5] == "1234,50" for f in leidas)


def test_inv043_csv_texto_normal_con_comas_no_cambia_y_montos_y_xlsx_no_se_tocan(client):
    sembrar(descripcion="pan, leche, huevos", monto=1234.5, fecha="2026-11-01")
    sembrar(descripcion="x,=1+1", monto=-5, fecha="2026-11-02")
    f = filas_csv(pedir(client, desde="2026-11"))
    assert f[1][3] == "pan, leche, huevos" and f[1][5] == "1234,50"
    assert f[2][3] == "x,'=1+1"
    celdas = [c for fila in hoja_xlsx(pedir(client, desde="2026-11", formato="xlsx")).iter_rows(min_row=2)
              for c in fila]
    assert "x,=1+1" in [c.value for c in celdas]    # el xlsx conserva el texto original (quotePrefix solo al inicio)


# ── Ciclo 2: H5 año acotado ───────────────────────────────────────────────────

@pytest.mark.parametrize("params", [{"desde": "0000-01"}, {"desde": "9999-12"}, {"desde": "1999-12"},
                                    {"desde": "2026-11", "hasta": "2101-01"}])
def test_h5_anio_fuera_de_2000_2100_responde_422_sin_consumir_el_limite(client, params):
    for _ in range(12):   # más que el límite de 10 por minuto
        r = pedir(client, A, **params)
        assert r.status_code == 422 and r.json()["detail"] == "Formato de mes inválido (YYYY-MM)"
    assert pedir(client, A, desde="2026-11").status_code == 200   # el límite no se consumió


def test_h5_los_extremos_2000_01_y_2100_12_son_validos(client):
    assert pedir(client, A, desde="2000-01", hasta="2000-03").status_code == 200
    assert pedir(client, A, desde="2100-10", hasta="2100-12").status_code == 200


# ── Ciclo 2: menores del validador ────────────────────────────────────────────

def test_el_401_de_sesion_va_sin_cache_y_con_nosniff(client):
    for headers in ({}, {"Authorization": "Bearer basura"}, {"Authorization": "Basic abc"}):
        r = client.get(URL, params={"desde": "2026-11"}, headers=headers)
        assert r.status_code == 401
        assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"
        assert set(r.json()) == {"detail"}
