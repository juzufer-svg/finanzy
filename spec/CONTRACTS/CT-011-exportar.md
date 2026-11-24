# CT-011 — Exportar transacciones `/api/v1/exportaciones`

- **Versión:** v1 (CHG-018, ciclo 2) · **UC:** UC-015 · **REQ:** F-019 · **ADR:** ADR-011 · **INV:** INV-042 a INV-045 (y INV-001)
- **Permiso requerido:** sesión vigente (INV-016; errores comunes 401/503 en CT-002). El usuario sale **siempre** de la sesión (INV-001, INV-042); no existe parámetro de usuario y cualquiera que se envíe se ignora.
- Solo lectura (GET). Pasa por el proxy de Next.js con la cookie de sesión (ADR-005). **Qué falta hoy en el proxy (ADR-011):** reenviar `Content-Disposition` solo para `exportaciones/*` y declarar `maxDuration = 10`; el binario ya pasa intacto (`arrayBuffer()`), `Cache-Control: no-store` ya lo pone el proxy y `X-Content-Type-Options: nosniff` sale de `next.config.js`.

## Endpoint
| Endpoint | Entrada (query) | Respuesta |
|---|---|---|
| `GET /exportaciones/transacciones` | `desde` = `YYYY-MM` (obligatorio, INV-005) · `hasta` = `YYYY-MM` (opcional; por defecto = `desde`) · `formato` = `csv` \| `xlsx` (opcional; por defecto `csv`) | 200 con el archivo |

Rango: del primer día de `desde` al último día de `hasta` (ambos meses incluidos). Se permiten meses futuros (archivo solo con encabezados).

## Topes (INV-044)
**12 meses · 10 000 filas · 4 MB (4 000 000 bytes) de archivo.** Se comprueban en el servidor; nunca se entrega un archivo truncado ni parcial. El tope de 4 MB existe porque Vercel responde **413 opaco** (sin JSON) por encima de ~4,5 MB de respuesta de función; así el usuario siempre ve el error claro del backend.

## Errores
| HTTP | Cuándo | `detail` |
|---|---|---|
| 401 / 503 | Sesión inválida o BD caída al verificarla (CT-002) | los de CT-002 |
| 422 | `desde` o `hasta` con formato inválido | "Formato de mes inválido (YYYY-MM)" |
| 422 | `desde` posterior a `hasta` | "El mes inicial no puede ser posterior al final" |
| 422 | Más de 12 meses | "Puedes exportar hasta 12 meses por archivo" |
| 422 | `formato` distinto de `csv`/`xlsx` | "Formato no válido: usa csv o xlsx" |
| 422 | Más de 10 000 transacciones en el rango (no se trunca nunca, INV-044) | "Hay más de 10 000 transacciones en ese rango. Elige menos meses." (+ `"codigo": "exportacion_demasiadas_filas"`) |
| 422 | El archivo superaría 4 000 000 bytes (se comprueba **mientras genera**; sin truncar) | "El archivo superaría los 4 MB. Elige menos meses." (+ `"codigo": "exportacion_demasiado_grande"`) |
| 429 | Más de 10 descargas por minuto por usuario | "Demasiadas descargas. Espera un momento e intenta de nuevo." |
| 503 | La BD falla al leer las transacciones (se propaga, INV-013; no se devuelve un archivo parcial) | "Servicio no disponible. Intenta de nuevo en unos minutos." |
| 503 | La exportación tarda más de 8 s en total (REQ-N-019) | "La exportación tardó demasiado. Elige menos meses." |

Los 422 de tope añaden el campo `codigo` (aditivo; `detail` sigue siendo texto): `exportacion_demasiadas_filas` y `exportacion_demasiado_grande`.

## Cabeceras de la respuesta 200
- `Content-Type`: `text/csv; charset=utf-8` o `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- `Content-Disposition: attachment; filename="finanzy-transacciones-2026-11.csv"` (un mes) o `filename="finanzy-transacciones-2026-01_a_2026-11.xlsx"` (rango). Solo ASCII; **sin** nombre, correo ni ids (INV-042).
- `Cache-Control: no-store` · `X-Content-Type-Options: nosniff`.
- El proxy reenvía `Content-Type` y, solo en `exportaciones/*`, `Content-Disposition` (función `cabecerasDeDescarga`, probada en `frontend/tests/exportar.test.mjs`); en las demás rutas solo `Content-Type`.

## Cómo debe leer el frontend las respuestas (con `responseType: 'blob'`)
Con `responseType: 'blob'`, un 422/429/503 llega como `Blob`, no como objeto: `errorDeBlob(err)` (`frontend/lib/exportar.ts`) lee el `Blob` como texto, lo interpreta como JSON (`detail`, `codigo`) y lo asigna a `err.response.data`; después se usa `apiErrorMessage` y `useDialog()`. Si el cuerpo no es JSON (p. ej. el 413 opaco de Vercel) se usa un mensaje por defecto («El archivo es demasiado grande. Elige menos meses.» para 413). Un 401 lo gestiona el interceptor de `apiClient` como en el resto de la app.

## Columnas (en este orden; los encabezados son texto fijo)
| # | Encabezado | Contenido |
|---|---|---|
| 1 | Fecha | `AAAA-MM-DD` (xlsx: fecha real con formato `aaaa-mm-dd`) |
| 2 | Tipo | `Ingreso` o `Gasto` |
| 3 | Categoría | Nombre de la categoría del usuario, o `Sin categoría` |
| 4 | Descripción | Texto de la transacción (vacío si no tiene) |
| 5 | Medio de pago | `Débito`, `Crédito`, `Efectivo`, `Transferencia`, `Nequi / Daviplata` o vacío |
| 6 | Monto (COP) | Monto **tal como está guardado** en COP, 2 decimales, sin convertir a la moneda de visualización (INV-045). CSV: `1234,50`; xlsx: número con formato `#,##0.00` |
| 7 | Origen | `App` o `WhatsApp` (existe fila en `whatsapp_registros`). Recurrentes y abonos a metas salen como `App` (**decisión del dueño**; «Recurrente» exigiría una columna `origen` en `transacciones`: otro cambio) |

**v1.1 (CHG-019, fase c):** se añade al final la columna 8 **Cuenta** (nombre de la cuenta de dinero o vacío). Cambio aditivo: no cambia las columnas 1 a 7. Las transferencias entre cuentas **no** se incluyen (no son ingreso ni gasto, INV-049). La columna Cuenta cuenta para el tope de 4 MB.

Orden de las filas: fecha ascendente, luego fecha de creación, luego id. Sin filas: solo la fila de encabezados.

## Formato
- **CSV:** UTF-8 con BOM (`﻿`), separador `;`, saltos `\r\n`, campos con `;`, comillas o saltos de línea entre comillas dobles (comillas internas duplicadas). Monto con coma decimal. **Riesgo documentado (decisión del dueño de mantenerlo):** en un Excel con configuración regional en inglés el `;` no separa columnas y la coma decimal puede leerse como texto; **el `.xlsx` es el formato seguro**. La interfaz muestra junto al botón de descarga: «Si tu Excel está en inglés y el CSV se ve en una sola columna, descarga el .xlsx.»
- **xlsx:** una hoja llamada `Transacciones`, fila 1 con los encabezados; números y fechas reales; todo texto como **cadena explícita** (nunca fórmula).
- **Neutralización (INV-043), distinta por formato:** todo **texto** (columnas 2 a 5 y 7, y la 8 en v1.1) que empiece por `=`, `+`, `-`, `@`, tabulación (`\t`) o retorno de carro (`\r`):
  - **CSV:** se escribe con un apóstrofo delante (`'=SUMA(A1)`); es la única defensa posible en un CSV.
  - **xlsx:** **sin apóstrofo visible**: la celda es una cadena explícita con el estilo `quotePrefix` activado (el valor guardado es el texto original). Un texto normal no se modifica en ninguno de los dos.
  - Fecha y monto no son texto y no se tocan.

## Compatibilidad
Añadir columnas solo al final (como la 8). Cambiar el orden, quitar columnas, subir los topes (12 meses, 10 000 filas, 4 MB) o cambiar el separador exige nueva versión y ADR. El frontend depende del nombre de archivo de `Content-Disposition`, de `detail` como texto y del campo `codigo` solo como complemento.
