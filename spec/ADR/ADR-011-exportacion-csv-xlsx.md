# ADR-011 — Exportación de transacciones a CSV y Excel (.xlsx) y dependencia `openpyxl`

- **Estado:** propuesta (spec de CHG-018, pendiente de aprobación; formatos y alcance ya decididos por el dueño el 2026-11-24)
- **Fecha:** 2026-11-24 · **Decide:** dueño del proyecto

## Contexto
REQ-F-019 pide descargar las transacciones del mes (o de un rango) en CSV y Excel. Hasta ahora «importación/exportación
de archivos» estaba fuera de alcance (REQUIREMENTS §4) y el backend no tiene librería para `.xlsx`. Los archivos
contienen datos financieros que salen de la app y texto libre del usuario (riesgo de **inyección de fórmulas**).

## Alternativas evaluadas
| Opción | Pros | Contras |
|---|---|---|
| Solo CSV | Sin dependencias | El dueño pidió también Excel |
| Generar `.xlsx` a mano con `zipfile` | Sin dependencias | Frágil (archivos que Excel «repara»); más código que mantener |
| `XlsxWriter` | Sin dependencias transitivas, muy rápido, escritura explícita de cadenas | Solo escribe: las pruebas necesitarían una segunda librería para leer el archivo |
| **`openpyxl` en modo de solo escritura** (elegida) | Escribe y lee (las pruebas abren el archivo y comprueban que no hay fórmulas); estándar; poca memoria en `write_only`; licencia MIT | Una dependencia transitiva (`et-xmlfile`); por defecto trata como fórmula un texto que empieza por `=` (se neutraliza, INV-043) |
| Exportar desde el frontend (JS) | Sin backend | Duplica reglas, repite el problema de dos fuentes de cifras y el filtro por usuario iría en el navegador |

## Decisión
1. Endpoint del backend `GET /api/v1/exportaciones/transacciones` (CT-011): el filtro por usuario sale de la sesión (INV-001, INV-042), no de la interfaz.
2. **CSV** (decisiones provisionales del coordinador, el dueño puede cambiarlas): UTF-8 **con BOM**, separador `;`, `\r\n`, comillas RFC 4180, monto con coma decimal y sin miles, fecha `AAAA-MM-DD`. **Excel (.xlsx)** con `openpyxl` `write_only`: números y fechas reales, textos siempre como cadena.
3. **Neutralización de fórmulas (INV-043):** en CSV y xlsx, todo texto que empiece por `=`, `+`, `-`, `@`, tabulación o retorno de carro se prefija con `'`. En xlsx además se fuerza el tipo cadena de cada celda de texto. Los números y fechas no son texto y no se prefijan.
4. **Dependencia:** añadir `openpyxl` (última versión estable 3.1.x al implementar, **fijada con `==`**) a `requirements.txt` y `requirements-dev.txt`; `python -m pip_audit -r requirements.txt` debe dar 0 vulnerabilidades antes de cerrar (REQ-N-004, REQ-N-021). Sin costo (REQ-N-006).
5. **Límites explícitos (INV-044):** ≤ 12 meses, ≤ 10 000 filas (cabe en < 4 MB con descripciones de 255 caracteres; Vercel corta las respuestas de función alrededor de 4,5 MB), paginando de 1000 en 1000 porque PostgREST corta ahí en silencio; si se supera, 422 con mensaje claro.
6. **Proxy:** para `exportaciones/*` reenvía además `Content-Disposition` y `Cache-Control` y devuelve el cuerpo binario sin convertirlo a texto. Resto de rutas sin cambio (INV-020 intacto: la sesión sigue en la cookie HttpOnly).
7. **Cabeceras:** `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Content-Disposition: attachment` con nombre genérico (sin nombre ni correo).
8. **Origen:** solo «App» o «WhatsApp» (WhatsApp = existe fila en `whatsapp_registros`). «Recurrente» y «Abono a meta» no se pueden distinguir hoy: requerirían una columna `origen` en `transacciones` (otro cambio).
9. Los **reportes no se recalculan** en el backend (dos fuentes de cifras): se exportan las transacciones del período.

## Consecuencias
- Positivas: el dueño y los usuarios pueden llevarse sus datos y analizarlos en Excel; sin servicios nuevos ni costo.
- Negativas / deuda aceptada: una dependencia más que auditar y actualizar; tope de 10 000 filas por archivo; la paginación no es una instantánea (INV-044); sin importación.
- Impacto en spec, código y pruebas: REQUIREMENTS §4 (se saca **solo exportar** de «Fuera»), REQ-F-019, CT-011, INV-042 a INV-045, `backend/tests/test_exportar.py`, `frontend/tests/exportar.test.mjs`, proxy de Next.js, `requirements*.txt`.
