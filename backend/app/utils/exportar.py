"""
Generación de los archivos de exportación de transacciones (CHG-018, CT-011, ADR-011).

Funciones SÍNCRONAS pensadas para correr en un hilo (REQ-N-026): la lectura paginada y la escritura no deben
bloquear el bucle de eventos.

- CSV: UTF-8 con BOM, «;», `\\r\\n`, monto SIN comillas y con coma decimal. TODA celda de texto va entre comillas y,
  si empieza por = + - @ tab o CR, lleva un apóstrofo delante, y lo mismo el fragmento que siga a un «,» «;» o salto de línea interno
  (INV-043; única defensa posible en un CSV, que por eso altera mínimamente esos textos; la defensa fuerte es el xlsx).
  La columna 8 «Cuenta» (CHG-025) es texto del usuario como las demás: mismas defensas y cuenta para el tope de bytes.
- xlsx (openpyxl, solo escritura): números y fechas reales; todo texto es una cadena explícita y, si podría leerse
  como fórmula, lleva el estilo `quotePrefix` SIN apóstrofo visible (INV-043).
- Topes (INV-044): 10 000 filas y 4 000 000 bytes; nunca se entrega un archivo truncado. Se lee de 1000 en 1000
  (PostgREST corta ahí en silencio) y se comprueban filas, bytes y plazo entre página y página.
"""
import os
import re
import tempfile
import threading
import time
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Iterator, Optional

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

MAX_FILAS = 10_000
MAX_BYTES = 4_000_000
TAMANO_PAGINA = 1000
PLAZO_SEGUNDOS = 8.0
FILAS_ENTRE_COMPROBACIONES = 500   # el bucle de escritura del xlsx también respeta `detener` y el plazo

ENCABEZADOS = ("Fecha", "Tipo", "Categoría", "Descripción", "Medio de pago", "Monto (COP)", "Origen", "Cuenta")
NOMBRE_HOJA = "Transacciones"
SIN_CATEGORIA = "Sin categoría"

TIPOS = {"ingreso": "Ingreso", "gasto": "Gasto"}
MEDIOS_PAGO = {
    "debito": "Débito", "credito": "Crédito", "efectivo": "Efectivo",
    "transferencia": "Transferencia", "nequi_daviplata": "Nequi / Daviplata",
}
_PELIGROSOS = ("=", "+", "-", "@", "\t", "\r")

TIPO_CSV = "text/csv; charset=utf-8"
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ExportacionDemasiadasFilas(Exception):
    """Más de 10 000 transacciones en el rango."""


class ExportacionDemasiadoGrande(Exception):
    """El archivo superaría 4 000 000 bytes."""


class ExportacionLenta(Exception):
    """Se agotó el plazo total (8 s) o la petición fue cancelada."""


def es_peligroso(texto: str) -> bool:
    """¿Un programa de hojas de cálculo podría leer este texto como fórmula? (INV-043)"""
    return texto.startswith(_PELIGROSOS)


# Separador («,» «;» o salto de línea) seguido de espacios o comillas (opcionales) y un carácter peligroso: el apóstrofo va
# justo tras el separador, de modo que la celda que un lector abra tras él empiece por «'» aunque lleve comillas delante.
_FRAGMENTO_PELIGROSO = re.compile(r"([,;\r\n])([ \"]*)(?=[=+\-@\t\r])")


def neutralizar_csv(texto: str) -> str:
    """Apóstrofo delante de un texto peligroso y delante de todo fragmento peligroso que siga a un «,» «;» o salto de
    línea interno, con o sin espacios y comillas (`x,=1+1` -> `x,'=1+1`): leído con «,» o «;» no queda ninguna celda
    que empiece como fórmula.
    Un texto normal (p. ej. «pan, leche») no se toca."""
    texto = _FRAGMENTO_PELIGROSO.sub(r"\1'\2", texto)
    return "'" + texto if es_peligroso(texto) else texto


def _monto(valor) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalizar(fila: dict, categorias: dict, cuentas: Optional[dict] = None) -> tuple:
    """(fecha, tipo, categoría, descripción, medio de pago, monto, origen, cuenta) en el formato del archivo.
    Una categoría que no sea del usuario sale como «Sin categoría» (INV-042); nunca se exportan ids. La cuenta de dinero
    (columna 8, CHG-025) sale por su nombre y queda vacía si no tiene cuenta o no es del usuario."""
    categoria_id = fila.get("categoria_id")
    categoria = categorias.get(str(categoria_id)) if categoria_id else None
    cuenta_id = fila.get("cuenta_id")
    cuenta = (cuentas or {}).get(str(cuenta_id)) if cuenta_id else None
    return (
        str(fila["fecha"])[:10],
        TIPOS.get(fila.get("tipo"), ""),
        categoria or SIN_CATEGORIA,
        fila.get("descripcion") or "",
        MEDIOS_PAGO.get(fila.get("medio_pago"), ""),
        _monto(fila["monto"]),
        "WhatsApp" if fila.get("whatsapp") else "App",
        cuenta or "",
    )


def _revisar_plazo(limite: float, detener: Optional[threading.Event]) -> None:
    if (detener is not None and detener.is_set()) or time.monotonic() > limite:
        raise ExportacionLenta()


def _paginas(leer_pagina: Callable[[int, int], list], categorias: dict, limite: float,
              detener: Optional[threading.Event], cuentas: Optional[dict] = None) -> Iterator[list]:
    """Páginas de filas normalizadas. Pide de 1000 en 1000 hasta agotar y falla si hay más de 10 000 (sin truncar).
    Cualquier error de la BD se propaga (INV-013): nunca se entrega un archivo parcial."""
    leidas = 0
    while True:
        _revisar_plazo(limite, detener)
        pagina = leer_pagina(leidas, TAMANO_PAGINA)
        _revisar_plazo(limite, detener)
        leidas += len(pagina)
        if leidas > MAX_FILAS:
            raise ExportacionDemasiadasFilas()
        if pagina:
            yield [_normalizar(f, categorias, cuentas) for f in pagina]
        if len(pagina) < TAMANO_PAGINA:
            return


def _texto_csv(texto: str) -> str:
    """Celda de texto SIEMPRE entre comillas (las comillas internas se duplican) y neutralizada al inicio (INV-043).
    Entre comillas, una coma o un «;» dentro de la descripción no parte la celda en las lecturas estándar."""
    return '"' + neutralizar_csv(texto).replace('"', '""') + '"'


def _generar_csv(paginas: Iterator[list]) -> bytes:
    trozos = [b"\xef\xbb\xbf"]   # BOM de UTF-8 para que Excel detecte la codificación
    total = len(trozos[0])

    def bloque(filas: list) -> bytes:
        # Texto entre comillas (QUOTE_NONNUMERIC); el monto va SIN comillas y con coma decimal
        return "".join(
            ";".join([_texto_csv(f[0]), *(_texto_csv(x) for x in f[1:5]), str(f[5]).replace(".", ","),
                      _texto_csv(f[6]), _texto_csv(f[7])]) + "\r\n"
            for f in filas).encode("utf-8")

    trozos.append((";".join(_texto_csv(e) for e in ENCABEZADOS) + "\r\n").encode("utf-8"))
    total += len(trozos[-1])
    for filas in paginas:                     # se cuentan los bytes REALES tras cada página
        trozos.append(bloque(filas))
        total += len(trozos[-1])
        if total > MAX_BYTES:
            raise ExportacionDemasiadoGrande()   # deja de pedir páginas
    return b"".join(trozos)


def _texto_xlsx(hoja, texto: str) -> WriteOnlyCell:
    """Cadena explícita (nunca fórmula); si parece fórmula, con quotePrefix y sin apóstrofo."""
    texto = ILLEGAL_CHARACTERS_RE.sub("", texto)   # openpyxl rechaza caracteres de control
    celda = WriteOnlyCell(hoja, value=texto)
    celda.data_type = "s"
    if es_peligroso(texto):
        celda.quotePrefix = True
    return celda


def _limpiar_libro(libro, guardado: bool = False) -> None:
    """Cierra el libro y borra los temporales de sus hojas. `Workbook.close()` NO borra el temporal de cada hoja de solo
    escritura (openpyxl lo borra únicamente al guardar): si se corta antes de `save`, quedaría en /tmp hasta reiniciar.
    Si el libro ya se guardó no hay nada que limpiar, y ningún fallo de limpieza (OSError) debe tumbar un archivo ya
    generado."""
    if guardado:
        try:
            libro.close()
        except Exception:
            pass
        return
    try:
        libro.close()
    except Exception:
        pass
    finally:
        for hoja in getattr(libro, "_sheets", []):
            escritor = getattr(hoja, "_writer", None)
            ruta = getattr(escritor, "out", None)
            if not isinstance(ruta, str):
                continue
            try:
                filas = getattr(hoja, "_rows", None)
                if filas is not None:
                    filas.close()             # primero el generador de filas (si no, se queja al recolectarse)
                escritor.close()              # cierra el generador de lxml (puede quejarse si quedó a medias)
            except Exception:
                pass
            try:
                os.remove(ruta)
            except OSError:
                pass                          # ya no existe o no se puede borrar: no es motivo para fallar
            try:
                from openpyxl.worksheet import _writer as _escritor_hoja
                _escritor_hoja.ALL_TEMP_FILES.remove(ruta)
            except (ValueError, ImportError, AttributeError):
                pass


def _generar_xlsx(paginas: Iterator[list], limite: float, detener: Optional[threading.Event]) -> bytes:
    # Se lee TODO antes de tocar openpyxl: un fallo de la BD, el plazo o el tope de filas no deja un libro a medias.
    # La memoria está acotada por el tope de 10 000 filas (INV-044).
    paginas = list(paginas)
    libro = Workbook(write_only=True)   # crea archivos temporales: `close()` SIEMPRE, también si se corta por plazo
    ruta = None
    guardado = False
    try:
        hoja = libro.create_sheet(NOMBRE_HOJA)
        hoja.append(list(ENCABEZADOS))
        escritas = 0
        for filas in paginas:
            for fecha, tipo, categoria, descripcion, medio, monto, origen, cuenta in filas:
                if escritas % FILAS_ENTRE_COMPROBACIONES == 0:
                    _revisar_plazo(limite, detener)
                escritas += 1
                c_fecha = WriteOnlyCell(hoja, value=date.fromisoformat(fecha))
                c_fecha.number_format = "yyyy-mm-dd"
                c_monto = WriteOnlyCell(hoja, value=float(monto))
                c_monto.number_format = "#,##0.00"
                hoja.append([c_fecha, _texto_xlsx(hoja, tipo), _texto_xlsx(hoja, categoria),
                             _texto_xlsx(hoja, descripcion), _texto_xlsx(hoja, medio), c_monto,
                             _texto_xlsx(hoja, origen), _texto_xlsx(hoja, cuenta)])
        _revisar_plazo(limite, detener)
        descriptor, ruta = tempfile.mkstemp(suffix=".xlsx")
        os.close(descriptor)
        libro.save(ruta)
        guardado = True
        if os.path.getsize(ruta) > MAX_BYTES:    # se mide el archivo REAL que se entregaría
            raise ExportacionDemasiadoGrande()
        with open(ruta, "rb") as f:
            return f.read()
    finally:
        _limpiar_libro(libro, guardado)
        if ruta is not None:
            try:
                os.unlink(ruta)
            except OSError:
                pass


def generar_archivo(formato: str, leer_pagina: Callable[[int, int], list], categorias: dict,
                    detener: Optional[threading.Event] = None, plazo: Optional[float] = None,
                    cuentas: Optional[dict] = None) -> bytes:
    """Lee las transacciones paginando y devuelve el archivo (bytes). Síncrona: ejecutar en un hilo.

    `leer_pagina(inicio, cantidad)` devuelve filas con fecha, tipo, categoria_id, descripcion, medio_pago,
    monto, cuenta_id y whatsapp; `categorias` y `cuentas` son {id: nombre} SOLO del usuario. Lanza `ExportacionDemasiadasFilas`,
    `ExportacionDemasiadoGrande` o `ExportacionLenta`; los errores de la BD se propagan."""
    limite = time.monotonic() + (PLAZO_SEGUNDOS if plazo is None else plazo)
    paginas = _paginas(leer_pagina, categorias, limite, detener, cuentas)
    if formato == "xlsx":
        return _generar_xlsx(paginas, limite, detener)
    return _generar_csv(paginas)
