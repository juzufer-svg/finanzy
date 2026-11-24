# CT-011 — Exportar transacciones `/api/v1/exportaciones`

- **Versión:** v1 (CHG-018) · **UC:** UC-015 · **REQ:** F-019 · **ADR:** ADR-011 · **INV:** INV-042 a INV-045 (y INV-001)
- **Permiso requerido:** sesión vigente (INV-016; errores comunes 401/503 en CT-002). El usuario sale **siempre** de la sesión (INV-001, INV-042); no existe parámetro de usuario y cualquiera que se envíe se ignora.
- Solo lectura (GET). Pasa por el proxy de Next.js con la cookie de sesión (ADR-005); el proxy reenvía `Content-Disposition` y `Cache-Control` para esta ruta y entrega el cuerpo binario sin convertirlo a texto.

## Endpoint
| Endpoint | Entrada (query) | Respuesta |
|---|---|---|
| `GET /exportaciones/transacciones` | `desde` = `YYYY-MM` (obligatorio, INV-005) · `hasta` = `YYYY-MM` (opcional; por defecto = `desde`) · `formato` = `csv` \| `xlsx` (opcional; por defecto `csv`) | 200 con el archivo |

Rango: del primer día de `desde` al último día de `hasta` (ambos meses incluidos). Se permiten meses futuros (archivo solo con encabezados).

## Errores
| HTTP | Cuándo | `detail` |
|---|---|---|
| 401 / 503 | Sesión inválida o BD caída al verificarla (CT-002) | los de CT-002 |
| 422 | `desde` o `hasta` con formato inválido | "Formato de mes inválido (YYYY-MM)" |
| 422 | `desde` posterior a `hasta` | "El mes inicial no puede ser posterior al final" |
| 422 | Más de 12 meses | "Puedes exportar hasta 12 meses por archivo" |
| 422 | `formato` distinto de `csv`/`xlsx` | "Formato no válido: usa csv o xlsx" |
| 422 | Más de 10 000 transacciones en el rango (no se trunca nunca, INV-044) | "Hay más de 10 000 transacciones en ese rango. Elige menos meses." |
| 429 | Más de 10 descargas por minuto por usuario | "Demasiadas descargas. Espera un momento e intenta de nuevo." |
| 503 | La BD falla al leer las transacciones (se propaga, INV-013; no se devuelve un archivo parcial) | "Servicio no disponible. Intenta de nuevo en unos minutos." |

## Cabeceras de la respuesta 200
- `Content-Type`: `text/csv; charset=utf-8` o `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- `Content-Disposition: attachment; filename="finanzy-transacciones-2026-11.csv"` (un mes) o `filename="finanzy-transacciones-2026-01_a_2026-11.xlsx"` (rango). Solo ASCII; **sin** nombre, correo ni ids (INV-042).
- `Cache-Control: no-store` · `X-Content-Type-Options: nosniff`.

## Columnas (en este orden; los encabezados son texto fijo)
| # | Encabezado | Contenido |
|---|---|---|
| 1 | Fecha | `AAAA-MM-DD` (xlsx: fecha real con formato `aaaa-mm-dd`) |
| 2 | Tipo | `Ingreso` o `Gasto` |
| 3 | Categoría | Nombre de la categoría del usuario, o `Sin categoría` |
| 4 | Descripción | Texto de la transacción (vacío si no tiene) |
| 5 | Medio de pago | `Débito`, `Crédito`, `Efectivo`, `Transferencia`, `Nequi / Daviplata` o vacío |
| 6 | Monto (COP) | Monto **tal como está guardado** en COP, 2 decimales, sin convertir a la moneda de visualización (INV-045). CSV: `1234,50`; xlsx: número con formato `#,##0.00` |
| 7 | Origen | `App` o `WhatsApp` (existe fila en `whatsapp_registros`). Recurrentes y abonos a metas salen como `App` |

**v1.1 (CHG-019, fase c):** se añade al final la columna 8 **Cuenta** (nombre de la cuenta de dinero o vacío). Cambio aditivo: no cambia las columnas 1 a 7. Las transferencias entre cuentas **no** se incluyen (no son ingreso ni gasto, INV-049).

Orden de las filas: fecha ascendente, luego fecha de creación, luego id. Sin filas: solo la fila de encabezados.

## Formato
- **CSV:** UTF-8 con BOM (`﻿`), separador `;`, saltos `\r\n`, campos con `;`, comillas o saltos de línea entre comillas dobles (comillas internas duplicadas).
- **xlsx:** una hoja llamada `Transacciones`, fila 1 con los encabezados; todo texto como cadena.
- **Neutralización (INV-043):** todo **texto** (columnas 2 a 5 y 7, y la 8 en v1.1) que empiece por `=`, `+`, `-`, `@`, tabulación (`\t`) o retorno de carro (`\r`) se escribe con un apóstrofo delante (`'=SUMA(A1)`). Fecha y monto no son texto y no se tocan.

## Compatibilidad
Añadir columnas solo al final (como la 8). Cambiar el orden, quitar columnas, subir los límites o cambiar el separador exige nueva versión y ADR. El frontend depende del nombre de archivo de `Content-Disposition`.
