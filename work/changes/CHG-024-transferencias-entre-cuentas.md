# CHG-024 — Transferencias entre cuentas de dinero (fase b de CHG-019)

- **Estado:** en-implementación (ficha aprobada por el dueño el 2026-11-25)
- **Fecha:** 2026-11-25 · **Solicitante:** dueño
- **Riesgo:** alto · **Modo:** `completo` (dinero + migración + concurrencia). Clasificación heredada de CHG-019 §2; no se repite el clasificador.

## 1. Pedido original (literal, sin reinterpretar)
> CHG-019 fase (b): transferencias entre cuentas del mismo usuario (tabla propia `transferencias`, atómica, no cuenta como ingreso/gasto, saldo de cuentas las incluye, borrado revierte, reglas FZ001/FZ002, tarjeta de crédito exenta, sin cuentas archivadas ni ajenas). Modo completo. Solo ESPECIFICACIÓN en esta etapa: presentar al dueño para aprobar antes de implementar.

## 2. Spec que ya existe (no se reescribe)
REQ-F-020 CA-5 · INV-049 (y INV-046/047/048/050/051) · CT-012 §Transferencias · ADR-009 §A y puntos 3-5 · UC-016 · BDD-CUENTAS «Fase (b)». Aprobada por el dueño en CHG-019.

## 3. Ajustes que esta ficha propone (por lo aprendido en la fase a)
| # | Ajuste | Por qué |
|---|---|---|
| A1 | Migración `backend/sql/2026-11-25_transferencias.sql` (el plan decía `2026-11-24_`) | Orden real de migraciones |
| A2 | La migración reemplaza `cuenta_saldo_actual` y `cuentas_con_saldo` (`create or replace`) para sumar transferencias recibidas y restar enviadas; `fz001_saldo_cuentas` las usa sin cambios | Ya existen desde la fase (a) |
| A3 | `fz001_saldo_transferencias` BEFORE INSERT/DELETE con bloqueo de origen y destino ordenado por id; FZ002 bajo el bloqueo; REVOKE/GRANT solo a `service_role`, `search_path` fijo, idempotente | Mismo patrón de `fz001_saldo_transacciones` |
| A4 | Las transferencias usan el ejecutor propio `cuentas` (4 hilos, 503 sin encolar) y `relanzar_o_503`/`traducir`: FZ001/FZ002 → 409, 22003 → 422 «El monto es demasiado grande» | Cierre de I-1/M-1 de la fase a |
| A5 | `POST /transferencias` limitado a 30 por minuto por usuario (429), como las altas de cuentas | Hoy el CT-012 no lo dice |
| A6 | Eliminar una cuenta con transferencias → 409 «Archívala» (ya cubierto por las llaves compuestas `NO ACTION`; se añade prueba) | INV-050 |
| A7 | Fase (b) deja sin tocar WhatsApp, asistente, recurrentes, metas y exportación (no ven transferencias por construcción) | Es la fase (c) |
| A8 | Interfaz: botón «Transferir» y sección «Transferencias» (últimas, con eliminar) dentro de «Cuentas»; mensajes de error con `apiErrorMessage` | CT-012 solo dice «lista de movimientos» |

## 4. Preguntas abiertas
| # | Pregunta | Recomendación |
|---|---|---|
| Q1 | ¿Dónde se ven las transferencias? | En la página Cuentas, sección propia (A8); no se mezclan con Transacciones |
| Q2 | ¿Se permite fecha futura? | Sí, igual que las transacciones (el saldo cuenta todo, decisión Q-3) |
| Q3 | ¿Sacar de una tarjeta de crédito (adelanto) puede dejarla en negativo? | Sí, es la excepción ya aprobada |
| Q4 | ¿Editar una transferencia? | No: se elimina y se crea otra (ya aprobado) |

## 5. Plan de tareas (tras aprobar la ficha)
| Tarea | Alcance | Depende de | Estado | Ciclos |
|---|---|---|---|---|
| T5 | Migración A1-A3 + `09_comprobar_transferencias.sql` + concurrencia (20 transferencias; 20 A→B y 20 B→A sin interbloqueos) + `PLATAAPP_SCHEMA.sql` | — | hecha, pendiente de validar (2026-11-25) | 1 |
| T6 | Backend `/transferencias` (A4-A6, `DemoDB`) + `test_transferencias.py` | T5 | pendiente | 0 |
| T7 | Frontend (A8) + `PLATAAPP_SCHEMA.sql` + trazabilidad | T6 | frontend hecho (2026-11-25: `cuentas/page.tsx`, `lib/transferencias.ts`, `tests/transferencias.test.mjs`; eslint, tsc, 99 pruebas y build OK); falta `PLATAAPP_SCHEMA.sql` | 0 |
| T8 | Validador y revisor en paralelo (máx. 2 ciclos) | T5-T7 | pendiente | 0 |

## 6. Registro de ejecución
| Fecha | Agente | Acción | Resultado |
|---|---|---|---|
| 2026-11-25 | coordinador | Ficha creada | Esperando aprobación del dueño |
| 2026-11-25 | dueño | Aprueba la ficha y las 4 recomendaciones (Q1-Q4) | T5, T6 y T7 en paralelo (archivos distintos) |

## 7. Cierre
Pendiente.
