# CHG-027 — Rango de fechas permitido en transacciones y transferencias (BL-046)

- **Estado:** en-implementación (decisión explícita del dueño el 2026-11-25)
- **Fecha:** 2026-11-25 · **Solicitante:** dueño · **Riesgo:** medio (cambia una regla de validación sobre dinero) · **Modo:** `estandar` (ficha + generador + validador; la regla la fijó el dueño, no se inventa nada)

## 1. Pedido original (literal)
> Máximo un año de rango que Inicia en enero 2026

Aclarado con el dueño (preguntas con opciones, 2026-11-25): **fecha mínima = 1 de enero de 2026; fecha máxima = fecha de hoy + 365 días (la ventana se mueve cada día); aplica solo a transacciones y transferencias** (no a metas, presupuestos ni recurrentes).

## 2. Regla (nueva INV-063)
Una transacción o transferencia solo admite fechas `>= 2026-01-01` y `<= hoy + 365 días`, donde «hoy» es la fecha de Colombia (UTC−5 fijo, `contadores.hoy_colombia()`, como el resto de la app). Fuera de rango → **422** con mensaje claro en español: «La fecha debe estar entre el 1 de enero de 2026 y el {fecha máxima dd/mm/aaaa}». Se valida en el esquema Pydantic de crear y editar transacción y de crear transferencia (el servidor decide; el frontend solo ayuda con `min`/`max` en los `<input type=date>`).
- Datos existentes: se comprobó en producción (2026-11-25) que NINGUNA transacción ni recurrente cae fuera del rango (transacciones del 2026-05-01 al 2026-11-24), así que no queda nada sin poder editarse. Una edición que NO cambia la fecha de una transacción antigua no se rechaza por la fecha (no aplica hoy; se prueba).
- **Fuera de alcance:** BD (sin CHECK ni migración), metas, presupuestos, recurrentes (su `proxima_fecha`) y WhatsApp salvo lo que ya reutilice el mismo esquema: si el flujo de WhatsApp pasa una fecha de la IA fuera de rango, responde un mensaje fijo claro («La fecha está fuera del rango permitido») y no registra; si hoy WhatsApp ya valida fechas de otra forma, se alinea sin cambiar su comportamiento válido.
- La confirmación de recurrentes crea transacciones con fecha de la ocurrencia: debe seguir funcionando; si la ocurrencia queda fuera de rango, 422 claro sin avanzar la fecha (sin tocar el SQL).

## 3. Spec afectada
INV-063 (nueva) en `spec/05-INVARIANTS.md`; CT-003 (transacciones), CT-012 §Transferencias (422 de fecha), UC/BDD de transacciones y de cuentas (un escenario por borde: 2025-12-31 rechaza, 2026-01-01 acepta, hoy+365 acepta, hoy+366 rechaza, año 9999 rechaza); TRACEABILITY; REQ-F-005/REQ-F-020 solo si citan fechas.

## 4. Pruebas
Con reloj controlado (monkeypatch de `hoy_colombia`): bordes inferior y superior en crear y editar transacción y en crear transferencia; 422 con mensaje; el día de Colombia (no el UTC) decide el borde; editar sin cambiar la fecha no se rechaza; las pruebas existentes que usan fechas fuera del rango (p. ej. 2024 o 2025) se adaptan SIN DEBILITARLAS y cada cambio se justifica en el informe.

## 5. Plan de tareas
| Tarea | Alcance | Estado | Ciclos |
|---|---|---|---|
| T1 | Backend: esquemas, WhatsApp si aplica, pruebas | hecha (pendiente validación T3) | 0 |
| T2 | Frontend: `min`/`max` en los campos fecha de transacción y transferencia + prueba de lógica | pendiente (tras T1) | 0 |
| T3 | Validador (ejecuta y mide), trazabilidad y cierre de BL-046 | pendiente | 0 |

## 6. Registro de ejecución
| Fecha | Agente | Acción | Resultado |
|---|---|---|---|
| 2026-11-25 | dueño | Decide rango y alcance | Ficha creada; T1 en curso |
| 2026-11-25 | generador | T1 backend: `utils/rango_fechas.py`, esquemas, PUT, confirmar recurrente, WhatsApp, `tests/test_rango_fechas.py` (INV-063) | Hecha; ver informe |

## 7. Cierre
Pendiente. Despliegue: push a `main` con aprobación; sin SQL ni variables nuevas.
