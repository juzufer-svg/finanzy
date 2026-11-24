# ADR-009 — Cuentas de dinero con saldo derivado y transferencias en tabla propia

- **Estado:** propuesta (spec de CHG-019, pendiente de aprobación; convivencia con el medio de pago, saldo inicial manual y movimientos anteriores «sin cuenta» ya decididos por el dueño el 2026-11-24)
- **Fecha:** 2026-11-24 · **Decide:** dueño del proyecto

## Contexto
El dueño quiere saber cuánto dinero tiene en cada lugar (efectivo, ahorros, billetera digital, tarjeta) y mover dinero
entre ellos (REQ-F-020). Hoy `transacciones` solo tiene `tipo` (`ingreso`/`gasto`, INV-004) y un `medio_pago` opcional.
Restricciones: sin servicios nuevos ni costo (REQ-N-006); las reglas críticas viven en el backend y la BD (INV-008,
INV-026); todo se guarda en COP; «cuentas bancarias conectadas» sigue fuera de alcance.

## Alternativas evaluadas

### A. Cómo modelar una transferencia
| Opción | Pros | Contras |
|---|---|---|
| Tercer valor `tipo = 'transferencia'` en `transacciones` | Una sola tabla | Rompe INV-004 y su CHECK; **cada** consulta existente (resumen, presupuestos, reportes de `month-stats.ts`, asistente, WhatsApp) trataría la transferencia como gasto o la tendría que excluir a mano: un olvido falsea cifras sin avisar; además necesita dos cuentas, es decir, columnas extra solo para este tipo |
| Un **par de filas** (gasto en origen + ingreso en destino) | Los saldos salen solos | Contaminan resumen, presupuestos y reportes (se contarían como ingreso **y** gasto, lo contrario de lo pedido); hay que enlazar y borrar las dos mitades juntas; categorías sin sentido |
| **Tabla separada `transferencias`** (elegida) | Una fila = un hecho atómico (los dos saldos se mueven juntos); queda fuera de **todas** las consultas actuales por construcción (INV-049 se cumple sin tocar reportes); llaves compuestas garantizan que ambas cuentas son del mismo usuario; CHECK `origen <> destino` | La lista de movimientos y el saldo unen dos fuentes (acotado y probado) |

### B. Saldo guardado o derivado
| Opción | Pros | Contras |
|---|---|---|
| Columna `saldo_actual` mantenida por código o disparador | Lectura O(1) | Dos verdades que pueden desfasarse (editar, borrar, cascadas, fallos a medias); corrección difícil |
| **Derivado con agregación SQL** (elegida) | Sin desfase posible; nada que reparar; un solo cálculo | Coste proporcional a los movimientos de la cuenta: se acota con índices por `cuenta_id` (REQ-N-022); si algún día fuera lento se podría materializar con otro ADR |

### C. Dónde garantizar «sin saldo negativo salvo tarjeta» y la atomicidad
| Opción | Pros | Contras |
|---|---|---|
| Comprobar en la API y luego escribir | Simple | Dos gastos simultáneos pasan ambos la comprobación (carrera) |
| Función RPC por operación (como `abonar_meta`) | Atómica | Cada ruta nueva (WhatsApp, recurrentes, futuras) debe acordarse de llamarla |
| **Disparador de la BD con bloqueo** (elegida) | Cubre **todas** las rutas y las peticiones simultáneas; la API solo traduce el error | Más SQL y pruebas con PostgreSQL real |

## Decisión
1. **Tabla `cuentas`:** `id`, `usuario_id` (→ `users` `CASCADE`), `nombre` (1-100; único por usuario con índice sobre `lower(btrim(nombre))`), `tipo` (`efectivo`, `ahorros_corriente`, `billetera_digital`, `tarjeta_credito`; no editable), `saldo_inicial NUMERIC(12,2)`, `archivada boolean`, `created_at`; `UNIQUE (id, usuario_id)` para las llaves compuestas. **RLS activado sin políticas**, `revoke all` a `anon`/`authenticated` (patrón de INV-021/INV-036).
2. **`transacciones.cuenta_id`** (y `recurrentes.cuenta_id` en la fase c), opcional, con llave foránea **compuesta** `(cuenta_id, usuario_id) → cuentas (id, usuario_id)`: la BD impide usar la cuenta de otra persona, además de `_ensure_owner` (INV-046). `ON DELETE NO ACTION` (**no** `RESTRICT`: `RESTRICT` se comprueba al instante y rompería la cascada «borrar usuario» de REQ-F-013; `NO ACTION` se comprueba al final de la sentencia, cuando la cascada ya borró los movimientos). Filas existentes: `NULL`, la migración no las toca.
3. **Tabla `transferencias`** (fase b): `id`, `usuario_id` (`CASCADE`), `cuenta_origen_id`, `cuenta_destino_id` (llaves compuestas con `usuario_id`, `NO ACTION`), `monto NUMERIC(12,2) > 0`, `fecha`, `descripcion ≤ 255`, `created_at`, `CHECK (cuenta_origen_id <> cuenta_destino_id)`. Sin comisión. RLS igual que arriba.
4. **Saldo (INV-047)** = `saldo_inicial + Σ ingresos − Σ gastos` (de `transacciones` con esa cuenta) `+ Σ transferencias recibidas − Σ transferencias enviadas`, función SQL `cuentas_con_saldo(usuario)` (solo `service_role`), en COP, **todos** los movimientos registrados sin mirar su fecha. Índices: `transacciones(cuenta_id)`, `transferencias(cuenta_origen_id)`, `transferencias(cuenta_destino_id)`.
5. **Regla de saldo y bloqueo (INV-048):** disparadores `AFTER` sobre `transacciones` (insertar, actualizar `monto`/`tipo`/`cuenta_id`, borrar), `transferencias` y `cuentas` (actualizar `saldo_inicial`) que (i) bloquean con `SELECT … FOR UPDATE` las cuentas afectadas **ordenadas por id** (evita interbloqueos), (ii) recalculan el saldo con una consulta nueva (en `READ COMMITTED` la segunda petición ve lo confirmado por la primera) y (iii) si una cuenta que **no** es `tarjeta_credito` queda en negativo lanzan un error con SQLSTATE propio (`FZ001`, `saldo_negativo`) que revierte toda la sentencia. Otros errores propios: `FZ002` cuenta archivada, `FZ003` tope de 20 cuentas (comprobado con `pg_advisory_xact_lock` por usuario). **El disparador no comprueba nada si el usuario ya fue borrado** (cascada de REQ-F-013); se prueba. El backend traduce `FZ001/FZ002/FZ003` a 409 con mensaje claro y nunca los deja pasar como 500.
6. **Archivada = congelada:** no admite altas, cambios de monto/tipo/cuenta ni bajas de movimientos ni transferencias (409). Se desarchiva para operar.
7. **Eliminar:** solo cuentas sin movimientos ni transferencias; si no, 409 «archívala». Borrar el usuario borra todo (INV-021 ampliada).
8. **Montos (INV-051):** `NUMERIC(12,2)` admite hasta 9 999 999 999,99 y INV-003 permite 1e12 (BL-017 sin resolver: valores entre ambos darían error de la BD). Para lo nuevo el backend exige ≤ 9 999 999 999,99 y 2 decimales (422 claro); `saldo_inicial` puede ser negativo **solo** en `tarjeta_credito` (deuda inicial). Esto **no** cambia INV-003: se recomienda cerrar BL-017 antes de la fase (a).
9. **Medio de pago y cuenta coexisten** y son independientes (no se valida uno contra otro). «Transferencia» (medio de pago) no es «transferencia entre cuentas» (glosario).
10. **Modo demo:** `demo_db.py` implementa las mismas reglas para que `backend/tests/` las verifique; la atomicidad y la concurrencia reales se prueban en PostgreSQL (`backend/sql/pruebas/08`, `09`, `10` y `probar.sh`, patrón de CHG-004/CHG-017).
11. **Migraciones por fase**, idempotentes (`if not exists`, `create or replace`), ejecutadas en Supabase **antes** del backend correspondiente. La fase (c) reemplaza `abonar_meta` por una versión con `p_cuenta_id uuid default null` (se elimina la firma anterior para no crear ambigüedad); el backend sigue funcionando con la versión vieja hasta aplicar el SQL, pero **sin** cuenta de origen (con cuenta y sin la función nueva responde 503, nunca usa el método anterior, que no es atómico).
12. **Integraciones (fase c):** abono, recurrentes y WhatsApp aceptan cuenta **opcional**; WhatsApp resuelve por nombre entre las cuentas activas del usuario y la IA recibe solo nombres (nunca ids ni saldos, INV-029); el asistente gana una herramienta de solo lectura (INV-023); la exportación añade la columna Cuenta al final (CT-011 v1.1).

## Consecuencias
- Positivas: saldos siempre coherentes, imposible un saldo negativo indebido ni siquiera con peticiones simultáneas ni desde WhatsApp; los reportes existentes no cambian (las transferencias no están en `transacciones`).
- Negativas / deuda aceptada: más SQL y disparadores que mantener; el cálculo de saldo crece con los movimientos (índices; revisar si pasa de REQ-N-022); sin cupo de tarjeta, sin comisiones, sin edición de transferencias, sin saldo histórico, sin conversión de tipo de cuenta; el tope de 9 999 999 999,99 de lo nuevo convive con el 1e12 de INV-003 hasta cerrar BL-017.
- Impacto en spec, código y pruebas: INV-046 a INV-052 (y ampliación de INV-021 e INV-008); CT-012 y campos aditivos en CT-003/006/007/008/009/011; `backend/tests/test_cuentas.py`, `test_transferencias.py`, `test_cuentas_integracion.py`; `backend/sql/pruebas/08`, `09`, `10`; frontend (página «Cuentas», formularios, lista de movimientos).
