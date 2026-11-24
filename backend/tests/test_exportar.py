"""CHG-018 · REQ-F-019 · INV-042 a INV-045 · REQ-N-019, N-020, N-026: exportar transacciones (BDD-EXPORTAR, CT-011)."""
import asyncio
import csv
import io
import random
import re
import time
import uuid
import zipfile
from datetime import datetime, timezone

import httpx
import pytest
from openpyxl import load_workbook

from app.main import app
from app.models import demo_db, whatsapp as whatsapp_db
from app.models.plataapp import TransaccionDB
from app.utils import exportar as generador
from conftest import auth_header

A = auth_header("user-a")
B = auth_header("user-b")
URL = "/api/v1/exportaciones/transacciones"
ENCABEZADOS = ["Fecha", "Tipo", "Categoría", "Descripción", "Medio de pago", "Monto (COP)", "Origen"]
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
    assert [f[3] for f in filas] == ["'" + d for d in PELIGROSAS]
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
    assert r.content.decode("utf-8-sig").split("\r\n")[0] == ";".join(ENCABEZADOS)
    filas = filas_csv(r)
    assert filas[0] == ENCABEZADOS
    assert [f[3] for f in filas[1:]] == ["primera; con punto y coma", 'con "comillas"', "tercera"]  # fecha ascendente
    assert filas[3] == ["2026-11-20", "Gasto", "Mercado", "tercera", "Débito", "1234,50", "App"]
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
    assert filas[1][3:] == ["por whatsapp", "Débito", "10,00", "WhatsApp"]
    assert filas[2][3:] == ["por la app", "", "10,00", "App"]
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
