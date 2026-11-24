# CHG-019 — Cuentas con saldo y transferencias

- **Estado:** en especificación (spec escrita, pendiente de validación y de aprobación del dueño; sin código)
- **Fecha:** 2026-11-24 · **Solicitante:** Julián Zúñiga (dueño)
- **Riesgo:** alto · **Modo:** completo (dinero, datos, migración SQL, concurrencia, contratos) · **BL:** BL-038

## 1. Pedido original (literal, sin reinterpretar)
> 2. Cuentas con saldo y transferencias: es lo que más cambia la utilidad diaria.

Contexto: el dueño pidió mejoras para Finanzy y eligió implementar inicialmente estas tres: «1. Exportar a Excel/CSV: rápido, útil y de bajo riesgo. 2. Cuentas con saldo y transferencias: es lo que más cambia la utilidad diaria. 3. Persistir los bloqueos de login en PostgreSQL: cierra la deuda de seguridad más importante.»

## 2. Clasificación
Tipo: nueva-funcionalidad con **cambio de modelo de datos**. Riesgo: **alto**. Modo: **completo**. Es el cambio más grande de los tres: tablas nuevas, columna nueva en `transacciones` y `recurrentes`, reglas de saldo con concurrencia (INV-008, INV-026), tres integraciones (metas, recurrentes, WhatsApp) y una de solo lectura (asistente, INV-023). Se entrega en **tres fases** con aprobación y despliegue por fase.
Cambia de spec: REQUIREMENTS §4 (cuentas **manuales**; «cuentas bancarias conectadas» sigue fuera) y REQ-F-020; INV-046 a INV-052; CT-012 (nuevo); CT-003, CT-006, CT-007, CT-008, CT-009 y CT-011 (campos aditivos); UC-016; ADR-009; BDD-CUENTAS; 02-ENTITIES, 04-STATES, 01-GLOSSARY; NFR REQ-N-022 a REQ-N-025.

## 3. Análisis
- **Qué es una «cuenta de dinero»** (término oficial; el glosario ya usa «Cuenta activa/pendiente» para la cuenta de **usuario**): un lugar donde la persona tiene dinero, creado a mano (efectivo, ahorros/corriente, billetera digital, tarjeta de crédito). No hay conexión con bancos: **«cuentas bancarias conectadas» sigue fuera de alcance**.
- **Convivencia con el medio de pago (CHG-007):** el medio de pago dice **cómo** se pagó (Débito, Crédito, Efectivo, Transferencia, Nequi / Daviplata); la cuenta dice **dónde está el dinero**. Los dos coexisten y son independientes: no se valida ni se deduce uno del otro. Ojo con el vocabulario: el medio de pago «Transferencia» no es una «transferencia entre cuentas» (glosario).
- **Saldo derivado, no guardado (INV-047):** `saldo = saldo inicial + ingresos − gastos + transferencias recibidas − transferencias enviadas` de los movimientos con esa cuenta, calculado en SQL, siempre en COP, solo el saldo **actual** (sin histórico). No existe columna de saldo actual que pueda desfasarse.
- **Movimientos anteriores:** quedan «sin cuenta» (`cuenta_id` NULL) y no mueven ningún saldo; la migración no toca datos existentes. La persona puede asignar una cuenta a un movimiento viejo editándolo (decisión explícita suya; entonces sí mueve el saldo).
- **Saldo negativo (INV-048):** solo la tarjeta de crédito puede quedar negativa (negativo = deuda); en las demás se rechaza con 409 claro y de forma **atómica**: un disparador de la BD (función SQL con `FOR UPDATE` sobre las cuentas afectadas, como INV-008) cubre **todas** las rutas (API, WhatsApp, recurrentes, `abonar_meta`) y las peticiones simultáneas.
- **Transferencias (INV-049):** entre dos cuentas propias distintas, sin comisión, **tabla separada** `transferencias` (ADR-009). No son ingreso ni gasto: no entran en resumen, presupuestos, reportes ni asistente (por construcción, porque no están en `transacciones`); sí aparecen en la lista de movimientos y mueven los saldos.
- **Ciclo de vida (INV-050):** una cuenta con movimientos no se elimina: se **archiva** (queda congelada y visible); sin movimientos se puede eliminar. Tope de 20 cuentas por usuario; nombre único por usuario.
- **Montos (INV-051):** hallazgo: `NUMERIC(12,2)` admite como máximo 9 999 999 999,99 mientras INV-003 permite hasta 1e12 (BL-017, pendiente). Para lo nuevo (saldo inicial, transferencias y transacciones **con cuenta**) el tope es 9 999 999 999,99 y 2 decimales, con 422 claro; INV-003 **no se modifica** (cambiarlo es una regla de negocio y BL-017 sigue pendiente).
- **Fases:** (a) cuentas + `cuenta_id` en transacciones + saldos + regla de saldo; (b) transferencias atómicas; (c) integración con metas, recurrentes, WhatsApp, asistente (solo lectura) y exportación (columna Cuenta).
- **Riesgos y cobertura:** doble contabilidad (se evita derivando); concurrencia de gastos simultáneos (disparador con bloqueo + prueba real en PostgreSQL con 30 gastos paralelos); borrado de usuario con cuentas (`ON DELETE NO ACTION` en la llave de `cuenta_id` —`RESTRICT` rompería la cascada de REQ-F-013— y el disparador omite la comprobación cuando el usuario ya se borró); cuentas ajenas (llave foránea compuesta `(cuenta_id, usuario_id)` además de `_ensure_owner`, INV-046); migración con NULL (idempotente, sin tocar filas); `abonar_meta` (se reemplaza la función con un parámetro opcional; el backend sigue funcionando con la anterior hasta aplicar el SQL); WhatsApp (INV-029: la IA solo propone el nombre, el backend resuelve y valida; sin saldos ni ids hacia Claude); latencia (índices por `cuenta_id`, REQ-N-022).

## 4. Preguntas abiertas
| # | Pregunta | Impacto | Respuesta | Quién |
|---|---|---|---|---|
| 1 | Medio de pago y cuenta | Modelo | **Coexisten** (2026-11-24) | Julián Zúñiga |
| 2 | Alta de cuentas y movimientos anteriores | Datos | Se crean con **saldo inicial manual**; los movimientos anteriores quedan **sin cuenta** y no mueven ningún saldo (2026-11-24) | Julián Zúñiga |
| 3 | Atributos de la cuenta | Modelo | **Decidido por defecto seguro; el dueño puede cambiarlo:** nombre (1-100, único por usuario sin distinguir mayúsculas ni espacios), tipo (`efectivo`, `ahorros_corriente`, `billetera_digital`, `tarjeta_credito`; **no editable**), saldo inicial, estado activa/archivada, tope de 20 cuentas por usuario (activas y archivadas) | coordinador |
| 4 | Saldo derivado en SQL, COP, solo actual | Diseño | **Decidido por defecto seguro:** derivado con agregación en SQL (INV-047); en COP; sin histórico | coordinador |
| 5 | Saldo negativo | Dinero | **Decidido por defecto seguro:** solo tarjeta de crédito; en las demás, 409 atómico por disparador con bloqueo (INV-048). Sin cupo/límite de la tarjeta en esta versión | coordinador |
| 6 | Transferencias | Modelo | **Decidido por defecto seguro:** tabla separada `transferencias` (ADR-009); sin comisión; no son ingreso ni gasto; se ven en la lista de movimientos; **se pueden crear y eliminar pero no editar** (se elimina y se crea otra); no se exportan en CT-011 v1.1; la IA de WhatsApp no las crea | coordinador |
| 7 | `cuenta_id` en transacciones | Contrato | **Decidido:** opcional (NULL = sin cuenta); propiedad validada al crear y editar (404, INV-046); en `PUT` como `medio_pago`: no enviar = conservar, `null` = quitar, valor = reemplazar | coordinador |
| 8 | Eliminar cuentas | Datos | **Decidido por defecto seguro:** con movimientos o transferencias, 409 «archívala»; sin ellos se puede eliminar. Una cuenta **archivada queda congelada**: no admite altas, cambios de monto/tipo/cuenta ni bajas de movimientos mientras esté archivada; se desarchiva para operar. Archivar con saldo distinto de 0 está permitido | coordinador |
| 9 | Qué movimientos cuentan en el saldo | Dinero | **Decidido por defecto seguro; el dueño puede cambiarlo:** **todos** los registrados con esa cuenta, sin mirar su fecha (incluidos los de fecha futura). Así el saldo no cambia solo con el paso del tiempo y la regla de no negativo es determinista | coordinador |
| 10 | Tope de montos de lo nuevo | Dinero | **Decidido:** 9 999 999 999,99 y 2 decimales (INV-051). INV-003 (1e12) y BL-017 no se tocan; recomendación: hacer BL-017 antes o junto a la fase (a) | coordinador (BL-017 requiere decisión del dueño) |
| 11 | Abonos a metas, recurrentes y WhatsApp | Integración | **Decidido por defecto seguro:** cuenta **opcional** en los tres. El abono puede indicar cuenta de origen (con saldo insuficiente no se suma a la meta ni se registra gasto, INV-008). La recurrente guarda `cuenta_id` opcional (confirmar puede cambiarla); si la cuenta está archivada o sin saldo, la confirmación falla y **no avanza** la fecha (INV-026). WhatsApp: la IA propone cuenta **solo si el usuario la nombra**; el backend la busca entre sus cuentas activas (sin distinguir mayúsculas ni tildes); si no existe o el saldo no alcanza **no registra** y lo explica; si no se nombra, sin cuenta | coordinador |
| 12 | Asistente | Seguridad | **Decidido:** una herramienta de **solo lectura** `cuentas_y_saldos` (INV-023); a Claude no se envían ids | coordinador |
| 13 | Terminología | Glosario | **Decidido:** «Cuenta de dinero» (código `cuentas`); la interfaz puede decir «Cuentas» en el menú. «Cuenta» sola sigue significando la cuenta de usuario en REQ-F-001/013 | coordinador |
| 14 | Pagar una tarjeta de crédito | Uso | Es una transferencia hacia la tarjeta (sube su saldo hacia 0); no hay flujo especial | coordinador |
| 15 | Fases (a)(b)(c) con despliegue separado y migraciones SQL propias (`2026-11-24_cuentas.sql`, `_transferencias.sql`, `_cuentas_integracion.sql`), ejecutadas **antes** de cada backend | Operación | **Decidido** | coordinador |

Preguntas que **requieren** respuesta del dueño: ninguna. Conviene su visto bueno explícito en la 9 (movimientos de fecha futura cuentan) y la 10 (tope 9 999 999 999,99 hasta resolver BL-017).

## 5. Spec afectada
`spec/REQUIREMENTS.md` (§4, REQ-F-020, §9), `spec/05-INVARIANTS.md` (INV-046 a INV-052; INV-021 y INV-008 ampliadas), `spec/CONTRACTS/CT-012-cuentas.md` (nuevo), CT-003 (v1.2 `cuenta_id`), CT-006, CT-007, CT-008, CT-009 (campos aditivos), CT-011 (v1.1), `spec/USE-CASES/UC-016-gestionar-cuentas-y-transferencias.md`, `spec/ADR/ADR-009-cuentas-y-transferencias.md`, `spec/BDD/BDD-CUENTAS.feature`, `spec/02-ENTITIES.md`, `spec/04-STATES.md`, `spec/01-GLOSSARY.md`, `spec/NFR/NFR.md` (REQ-N-022 a REQ-N-025), `spec/TRACEABILITY.md`, `work/BACKLOG.md` (BL-038) · **Aprobación de la spec:** pendiente

## 6. Plan de tareas
| Tarea | Alcance | Depende de | Estado | Ciclos |
|---|---|---|---|---|
| **Fase (a)** | | | | |
| T1 | Migración `backend/sql/2026-11-24_cuentas.sql` (tabla `cuentas` con RLS sin políticas, `transacciones.cuenta_id` con llave compuesta y `NO ACTION`, índices, disparadores de saldo/archivada/tope 20, función `cuentas_con_saldo`) + `backend/sql/pruebas/08_comprobar_cuentas.sql` + concurrencia real en `probar.sh` (30 gastos simultáneos) | spec aprobada; BL-017 recomendado | pendiente | 0 |
| T2 | Backend: `schemas`, `models` (`CuentaDB`, `DemoCuentaDB` con las mismas reglas), rutas `/cuentas` y `cuenta_id` en transacciones (traducción de errores SQL a 409/404), `backend/tests/test_cuentas.py` | T1 | pendiente | 0 |
| T3 | Frontend: página «Cuentas», selector «Cuenta (opcional)» en `TransactionForm`, saldos en la moneda de visualización, accesibilidad | T2 | pendiente | 0 |
| T4 | Validación + revisión independiente de la fase (a) + trazabilidad; despliegue (SQL antes) | T1-T3 | pendiente | 0 |
| **Fase (b)** | | | | |
| T5 | Migración `2026-11-24_transferencias.sql` (tabla, llaves compuestas, CHECK, disparador de saldo ampliado) + `09_comprobar_transferencias.sql` + concurrencia | fase (a) hecha | pendiente | 0 |
| T6 | Backend `/transferencias` + `backend/tests/test_transferencias.py` (incluye «no cuenta como ingreso ni gasto») | T5 | pendiente | 0 |
| T7 | Frontend: formulario de transferencia y su aparición en la lista de movimientos; validación + revisión + despliegue | T6 | pendiente | 0 |
| **Fase (c)** | | | | |
| T8 | Migración `2026-11-24_cuentas_integracion.sql` (`recurrentes.cuenta_id`, `abonar_meta` con `p_cuenta_id`) + `10_comprobar_cuentas_integracion.sql` | fase (b) hecha | pendiente | 0 |
| T9 | Backend: abono con cuenta, recurrentes, WhatsApp (resolución por nombre, INV-029), herramienta del asistente (INV-023), columna Cuenta en CT-011 v1.1 + `backend/tests/test_cuentas_integracion.py` | T8, CHG-018 | pendiente | 0 |
| T10 | Frontend de metas, recurrentes y exportación; validación + revisión independiente final + trazabilidad | T9 | pendiente | 0 |

Pruebas nombradas: ver INV-046 a INV-052 en `spec/05-INVARIANTS.md` y `spec/BDD/BDD-CUENTAS.feature`.

## 7. Registro de ejecución
| Fecha | Agente | Acción | Resultado / evidencia |
|---|---|---|---|
| 2026-11-24 | coordinador | Pedido registrado | Archivo creado |
| 2026-11-24 | clasificador | Clasificación | hallazgos revisados por el coordinador |
| 2026-11-24 | generador | Especificación (sin código) | REQ-F-020, CT-012, UC-016, ADR-009, INV-046 a INV-052, BDD, NFR y trazabilidad escritos. Hallazgos: choque de vocabulario «cuenta», `RESTRICT` rompería la cascada de usuario, `NUMERIC(12,2)` vs 1e12 |

## 8. Cierre
- **Aprobación humana final:** pendiente
