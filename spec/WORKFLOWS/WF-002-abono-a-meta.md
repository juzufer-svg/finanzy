# WF-002 — Abono a una meta

- **REQ / UC:** REQ-F-009 · UC-007
- **Disparador:** `POST /metas/{id}/abonar`

| Paso | Actor/Sistema | Acción | Decisión / condición | Si falla (compensación) |
|---|---|---|---|---|
| 1 | Backend | Validar que la meta exista y sea del usuario (INV-008) | No → 404, sin efectos | — |
| 2 | Backend | Buscar la categoría «Ahorro»; crearla si no existe | — | Error → 500 (sin gasto creado) |
| 3 | Backend | Crear la transacción de gasto | — | Error → 500 (sin cambios en la meta) |
| 4 | Backend | Sumar el monto a `monto_actual` | — | **Eliminar el gasto del paso 3** y responder 500 |

**Dependencias externas:** Supabase. **Idempotencia:** no es idempotente (cada llamada es un abono nuevo).
