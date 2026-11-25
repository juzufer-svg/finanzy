# CHG-025 — Integración de las cuentas con metas, recurrentes, WhatsApp, asistente y exportación (fase c de CHG-019)

- **Estado:** en-implementación (spec de la fase c aprobada por el dueño en CHG-019; el 2026-11-25 pidió implementarla completa: «implementar todo ese ajuste completo que quede full todo esta parte de la fase C»)
- **Fecha:** 2026-11-25 · **Solicitante:** dueño
- **Riesgo:** alto · **Modo:** `completo` (dinero, función SQL atómica nueva que reemplaza el flujo de confirmar recurrentes). Clasificación heredada de CHG-019.

## 1. Pedido original (literal)
> Si me gustaría implementar todo ese ajuste completo que quede full todo esta parte de la fase C

(Fase C explicada al dueño: abonos a metas con cuenta de origen, recurrentes con cuenta y confirmación atómica, WhatsApp con cuenta nombrada, asistente de solo lectura de cuentas y saldos, columna Cuenta en la exportación.)

## 2. Spec que ya existe (no se reescribe)
REQ-F-020 CA-7 · INV-052 · CT-012 §«Cambios aditivos» (CT-006 v1.1, CT-008 v1.1, CT-009 v1.1, CT-007 v1.1, CT-011 v1.1) · ADR-009 puntos 11-13 · BDD-CUENTAS fase (c) · UC-016.

## 3. Reglas para la implementación (lo aprendido en las fases a y b)
- Migración `backend/sql/2026-11-25_cuentas_integracion.sql`: `recurrentes.cuenta_id` (llave compuesta `(cuenta_id, usuario_id)` NO ACTION), `abonar_meta` con `p_cuenta_id uuid default null` (se elimina la firma anterior), función `confirmar_recurrente` con la firma de ADR-009 punto 13 (solo `service_role`, `search_path` fijo, idempotente), pruebas `10_comprobar_cuentas_integracion.sql` y concurrencia en `probar.sh` (2 confirmaciones simultáneas → 1 transacción; abono sin saldo no suma a la meta).
- Las llamadas a Supabase nuevas usan el ejecutor propio `cuentas` (4 hilos, 503 sin encolar) y `relanzar_o_503`/`traducir` (FZ001/FZ002 → 409, 22003/FZ004 → 422, nunca 500 ni texto crudo).
- Con `cuenta_id` y sin la función SQL nueva → 503, nunca el método anterior no atómico. Sin `cuenta_id`, todo se comporta como hoy.
- Columnas nuevas verificadas contra el esquema real (checklist 9); `PLATAAPP_SCHEMA.sql` idéntico a las migraciones.
- WhatsApp: la IA recibe solo NOMBRES de cuentas no archivadas; la cuenta solo se usa si el usuario la nombra; no crea transferencias (INV-029).
- Asistente: herramienta de solo lectura `cuentas_y_saldos` (INV-023).
- Exportación: columna 8 «Cuenta» al final (CT-011 v1.1); fórmulas neutralizadas como el resto de columnas de texto.

## 4. Preguntas abiertas
Ninguna que bloquee: todo está especificado y aprobado en CHG-019. Si el generador encuentra un vacío, lo lista y se pregunta al dueño (no se inventa).

## 5. Plan de tareas
| Tarea | Alcance | Depende de | Estado | Ciclos |
|---|---|---|---|---|
| T8 | Migración + `10_comprobar_cuentas_integracion.sql` + `probar.sh` + `PLATAAPP_SCHEMA.sql` | fase (b) hecha | hecha (pendiente de validar con T11) | 1 |
| T9 | Backend: abono, recurrentes (`confirmar_recurrente` atómica), WhatsApp, asistente, exportación + `test_cuentas_integracion.py` | T8 | pendiente | 0 |
| T10 | Frontend: metas, recurrentes, exportación (columna) y trazabilidad | contrato CT-012 (en paralelo con T9) | hecha (pendiente de validar con T11); la exportación no necesita cambio de UI (no lista columnas) | 1 |
| T11 | Validador y revisor en paralelo (máx. 2 ciclos) | T8-T10 | pendiente | 0 |

## 6. Registro de ejecución
| Fecha | Agente | Acción | Resultado |
|---|---|---|---|
| 2026-11-25 | dueño | Pide implementar la fase (c) completa | Ficha creada; T8 en curso |

## 7. Cierre
Pendiente. Despliegue (cuando llegue): SQL en Supabase ANTES del backend; sin variables nuevas; push a `main` solo con aprobación del dueño.
