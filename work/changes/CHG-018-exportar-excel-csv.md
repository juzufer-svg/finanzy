# CHG-018 — Exportar transacciones y reportes a Excel/CSV

- **Estado:** en especificación (spec escrita, pendiente de validación y de aprobación del dueño; sin código)
- **Fecha:** 2026-11-24 · **Solicitante:** Julián Zúñiga (dueño)
- **Riesgo:** medio-alto (el dueño lo describió como bajo, pero toca datos financieros fuera de la app, una dependencia nueva y el proxy) · **Modo:** completo · **BL:** BL-037

## 1. Pedido original (literal, sin reinterpretar)
> 1. Exportar a Excel/CSV: rápido, útil y de bajo riesgo.

Contexto: el dueño pidió mejoras para Finanzy y eligió implementar inicialmente estas tres: «1. Exportar a Excel/CSV: rápido, útil y de bajo riesgo. 2. Cuentas con saldo y transferencias: es lo que más cambia la utilidad diaria. 3. Persistir los bloqueos de login en PostgreSQL: cierra la deuda de seguridad más importante.»

## 2. Clasificación
Tipo: nueva-funcionalidad. Riesgo: **medio-alto**; modo: **completo**. Razón: los datos financieros salen de la app (privacidad, INV-001), hay riesgo de **inyección de fórmulas** en CSV/Excel, se añade una dependencia (ADR-011, `pip-audit`), cambia el proxy de Next.js (hoy solo reenvía `Content-Type` y no prevé descargas) y se amplía el alcance de REQUIREMENTS §4 (hoy «importación/exportación de archivos» está **fuera**).
Cambia de spec: REQUIREMENTS §4 (solo **exportar** sale de «Fuera»; importar sigue fuera) y REQ-F-019, CT-011, UC-015, ADR-011, INV-042 a INV-045, BDD-EXPORTAR, NFR REQ-N-019 a REQ-N-021.

## 3. Análisis
- **Qué se exporta:** solo **transacciones** (ingresos y gastos) del mes que la persona ve o de un rango de meses (hasta 12), en **CSV** o **Excel (.xlsx)**, con los montos en COP tal como se guardan (sin convertir a la moneda de visualización). Los **reportes no se recalculan** en el backend: hay dos fuentes de cifras (`frontend/lib/month-stats.ts` y el backend) y exportar solo transacciones evita que el archivo contradiga a la pantalla; la persona obtiene sus totales con una tabla dinámica o fórmulas propias.
- **Dónde:** botón «Descargar» en Transacciones y en Reportes (mismo período compartido, CHG-009).
- **Cómo:** endpoint autenticado `GET /api/v1/exportaciones/transacciones` (CT-011) en el backend; pasa por el proxy con la cookie; el usuario sale de la sesión, **nunca** de un parámetro (INV-001, INV-042). Ruta propia (no `/transacciones/exportar`) para no chocar con `GET /transacciones/{id}`.
- **Hallazgos del código:** (1) `TransaccionDB.obtener_por_usuario` hace una sola consulta sin paginar: PostgREST corta en 1000 filas **en silencio**; la exportación debe paginar con `range` y no puede heredar ese límite (INV-044). (2) `transacciones` no guarda el origen: «WhatsApp» se deduce de `whatsapp_registros`; las recurrentes confirmadas y los abonos a metas son transacciones normales, así que **no se pueden distinguir de «App»** sin cambiar el esquema (decisión 12, desviación respecto de la propuesta del coordinador). (3) El proxy (`frontend/app/api/v1/[...path]/route.ts`) dice «la API no usa redirecciones ni descargas»: hay que reenviar también `Content-Disposition` y `Cache-Control` y no tratar el cuerpo como texto. (4) Vercel limita la respuesta de una función a ~4,5 MB: de ahí el tope de 10 000 filas (REQ-N-020).
- **Riesgos de seguridad:** inyección de fórmulas (INV-043); fuga entre usuarios (INV-042, filtro por la sesión, sin ids ni correo en el archivo ni en el nombre); caché de un archivo con datos financieros (`no-store`); abuso de costo (límite de 10 descargas/min por usuario); dependencia nueva (ADR-011).
- **Integración con CHG-019:** cuando existan cuentas de dinero, CT-011 pasa a v1.1 con una columna **Cuenta al final** (cambio aditivo, no mueve las demás). Las transferencias entre cuentas no entran en el archivo de v1.1 (no son ingreso ni gasto, INV-049).

## 4. Preguntas abiertas
| # | Pregunta | Impacto | Respuesta | Quién |
|---|---|---|---|---|
| 1 | Formatos | Alcance | **CSV y Excel (.xlsx)** (2026-11-24) | Julián Zúñiga |
| 2 | Qué se exporta | Alcance | **Transacciones del mes que ve o de un rango de meses**, montos en COP como se guardan (2026-11-24) | Julián Zúñiga |
| 3 | CSV: separador y codificación | Interfaz | **Decidido por defecto seguro; el dueño puede cambiarlo:** separador «;», UTF-8 con BOM, saltos `\r\n`, monto con coma decimal y sin separador de miles (Excel en español lo abre como número), fecha `AAAA-MM-DD`. El xlsx guarda números y fechas reales | coordinador |
| 4 | Neutralización de fórmulas | Seguridad | **Decidido por defecto seguro:** toda celda de **texto** (descripción, categoría, etc.) que empiece por `=`, `+`, `-`, `@`, tabulación o retorno de carro se prefija con `'` en CSV y xlsx (INV-043). Los montos y fechas son numéricos y no se prefijan. En xlsx además todo texto se escribe como cadena, nunca como fórmula | coordinador |
| 5 | Rango y tope de filas | Rendimiento/seguridad | **Decidido por defecto seguro:** máximo **12 meses** y **10 000 filas** por archivo; si se supera, **422** con mensaje claro, sin truncar en silencio (INV-044). 10 000 filas caben en < 4 MB (límite de respuesta de Vercel ~4,5 MB) | coordinador |
| 6 | Paginación | Datos | **Decidido:** la exportación pagina de 1000 en 1000 hasta agotar o superar el tope (PostgREST corta en 1000) | coordinador |
| 7 | Endpoint y proxy | Seguridad | **Decidido por defecto seguro:** `GET /api/v1/exportaciones/transacciones` autenticado (INV-001/INV-042), por el proxy con cookie; `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Content-Disposition: attachment; filename="finanzy-transacciones-AAAA-MM.csv"` (o `AAAA-MM_a_AAAA-MM`) sin nombre ni correo. El proxy reenvía esas cabeceras y el cuerpo binario | coordinador |
| 8 | Descarga en la interfaz | Interfaz | **Decidido:** con `apiClient` (blob) y errores con `apiErrorMessage` + `useDialog()`; botón «Descargar» en Transacciones y Reportes con formato y rango (máx. 12 meses) | coordinador |
| 9 | Límite de frecuencia | Costo/abuso | **Decidido por defecto seguro:** 10 descargas por minuto por usuario (429), en memoria como el resto de límites de costo (INV-024); no protege secretos, solo recursos | coordinador |
| 10 | Dependencia `.xlsx` | Dependencias | `openpyxl` **no** es dependencia hoy. **Decidido en ADR-011:** añadir `openpyxl` (modo de solo escritura), fijada y con `pip-audit` limpio (REQ-N-004, REQ-N-021) también en `requirements-dev.txt` para leer el archivo en las pruebas. Costo US$0 | coordinador |
| 11 | Columnas | Contrato | **Decidido:** Fecha, Tipo, Categoría, Descripción, Medio de pago, Monto (COP), Origen; con CHG-019 se añade **Cuenta** al final. Orden: fecha ascendente, luego creación, luego id | coordinador |
| 12 | **Origen «recurrente»** que proponía el coordinador | Alcance | **No es posible sin cambiar el esquema** (una recurrente confirmada crea una transacción idéntica a las demás). **Decidido por defecto seguro:** Origen = «App» o «WhatsApp» (WhatsApp = existe fila en `whatsapp_registros`). Si el dueño quiere «Recurrente» (y «Abono a meta»), hace falta una columna `origen` en `transacciones` y su migración: sería otro cambio. **Es la única decisión del dueño que podría querer revisar** | coordinador (dueño puede cambiarlo) |
| 13 | Alcance de «Reportes» | Alcance | El botón de Reportes exporta las **transacciones** del mismo período, no las tablas calculadas; no se exportan presupuestos, metas ni recurrentes en esta versión | coordinador (dueño puede cambiarlo) |
| 14 | Instantánea | Datos | La paginación no es una instantánea: si se registra una transacción justo durante la descarga podría no entrar. Se acepta (uso personal) | coordinador |

Preguntas que **requieren** respuesta del dueño: ninguna. La 12 merece su visto bueno al aprobar la spec.

## 5. Spec afectada
`spec/REQUIREMENTS.md` (§3 nota, §4 alcance, REQ-F-019, §9), `spec/05-INVARIANTS.md` (INV-042 a INV-045), `spec/CONTRACTS/CT-011-exportar.md` (nuevo), `spec/CONTRACTS/CT-001-auth.md` (nota del proxy), `spec/USE-CASES/UC-015-exportar-transacciones.md`, `spec/ADR/ADR-011-exportacion-csv-xlsx.md`, `spec/BDD/BDD-EXPORTAR.feature`, `spec/NFR/NFR.md` (REQ-N-019 a REQ-N-021), `spec/01-GLOSSARY.md`, `spec/TRACEABILITY.md`, `work/BACKLOG.md` (BL-037) · **Aprobación de la spec:** pendiente

## 6. Plan de tareas
| Tarea | Alcance | Depende de | Estado | Ciclos |
|---|---|---|---|---|
| T1 | `openpyxl` en `requirements.txt`/`requirements-dev.txt` + `pip-audit`; `be/utils/exportar.py` (neutralización, CSV, xlsx) + `be/schemas/exportar.py` (validación de mes, rango y formato) + `be/models/plataapp.py` (consulta paginada con origen y categoría) + `be/api/routes/exportar.py` + `backend/tests/test_exportar.py` | spec aprobada | pendiente | 0 |
| T2 | Proxy: reenviar `Content-Disposition`, `Cache-Control` y cuerpo binario solo para `exportaciones/*`; `fe/lib/exportar.ts` (rango, nombre) + `frontend/tests/exportar.test.mjs` | T1 | pendiente | 0 |
| T3 | Interfaz: botón «Descargar» (formato, rango ≤ 12 meses) en Transacciones y Reportes, con `useDialog`, `ErrorState` y accesibilidad (`<label htmlFor>`, foco, `role="alert"`) + recorrido Playwright manual `frontend/e2e/exportar.mjs` | T2 | pendiente | 0 |
| T4 | Validación completa (pytest, eslint, build, `pip-audit`), revisión independiente, trazabilidad | T1-T3 | pendiente | 0 |

Pruebas nombradas: ver INV-042 a INV-045 en `spec/05-INVARIANTS.md` y `spec/BDD/BDD-EXPORTAR.feature`.

## 7. Registro de ejecución
| Fecha | Agente | Acción | Resultado / evidencia |
|---|---|---|---|
| 2026-11-24 | coordinador | Pedido registrado | Archivo creado |
| 2026-11-24 | clasificador | Clasificación | hallazgos revisados por el coordinador |
| 2026-11-24 | generador | Especificación (sin código) | REQ-F-019, CT-011, UC-015, ADR-011, INV-042 a INV-045, BDD, NFR y trazabilidad escritos. Hallazgo: `origen = recurrente` no es derivable (decisión 12) |

## 8. Cierre
- **Aprobación humana final:** pendiente
