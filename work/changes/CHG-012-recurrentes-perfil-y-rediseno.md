# CHG-012 — Recurrentes, copiar presupuestos, perfil, categorías, avisos y rediseño visual

- **Estado:** en revisión (falta el visto bueno del dueño y ejecutar el SQL en Supabase)
- **Fecha:** 2026-11-23 · **Solicitante:** dueño del proyecto
- **Riesgo:** medio (datos nuevos, contraseña y sesión) · modo `completo`

## 1. Pedido original
> Necesito que implementes A1 A3 A4 A5 A6. En las mejoras visuales implementarlas todas

(Propuesta previa: A1 recurrentes, A3 copiar presupuestos, A4 nombre y contraseña en el perfil, A5 página de
categorías, A6 avisos de presupuesto; B1 Inicio más útil, B2 botón «+» en el celular, B3 página pública, B4 modo
oscuro, B5 textos, B6 estados vacíos.)

## 2. Decisiones del dueño (2026-11-23, preguntas en el chat)
| Pregunta | Respuesta |
|---|---|
| ¿Las recurrentes se registran solas o se confirman? | **Pendientes por confirmar** (INV-025) |
| Frecuencias | **Mensual, quincenal y semanal** |
| Cambiar contraseña | **Pedir la actual y cerrar las demás sesiones** (INV-027) |
| Nombre de «Dashboard» | **Inicio** |

Decisiones técnicas propias (dentro de lo aprobado):
- Quincenal = dos días fijos al mes (día ancla y +15), no «cada 14 días»: así cae en las quincenas (15 y 30).
- Se guarda `dia_ancla` para que una recurrente del 31 vuelva al 31 después de febrero.
- Confirmar usa compare-and-set sobre `proxima_fecha` (un doble toque no registra dos veces).
- La contraseña actual incorrecta responde **400** (un 401 haría que el frontend cerrara la sesión) y suma al
  bloqueo del login (5 fallos → 15 min).
- La tabla `recurrentes` nace con RLS activo y sin políticas: solo la usa el backend con `service_role`.

## 3. Spec afectada
REQ-F-006 CA-4, REQ-F-007 CA-4/CA-5, REQ-F-014 CA-2/CA-3, REQ-F-016 (nuevo), alcance en REQUIREMENTS §4;
INV-025, INV-026, INV-027; CT-002 v1.1, CT-005 v1.1, CT-008 (nuevo); UC-012; BDD-RECURRENTES; TRACEABILITY.

## 4. Base de datos (ejecutar ANTES del despliegue)
`backend/sql/2026-11-23_recurrentes.sql` en Supabase → SQL Editor. Solo crea la tabla `recurrentes`; no toca datos.
Se puede repetir. Probado en PostgreSQL 16 local con `backend/sql/pruebas/probar.sh` (también corre en el CI).

## 5. Evidencia
- Backend: `python -m pytest -q` → 216 pruebas pasan (70 nuevas: `test_recurrentes.py`, `test_presupuestos_copia.py`, `test_perfil.py`).
- SQL: `probar.sh` → «OK: migraciones de huérfanos, medio de pago y recurrentes verificadas».
- Frontend: `npx eslint .` 0 problemas · `npm test` 24/24 · `npx next build` correcto.
- Recorrido real con Playwright (backend local con datos de ejemplo): login, Inicio, Recurrentes, Categorías,
  Presupuestos, Perfil y Transacciones en PC e iPhone 13, claro y oscuro; registrar una pendiente con monto
  ajustado; el botón «+» abre Transacciones con el foco en el monto.

## 6. Hallazgo (sin cambiar, requiere decisión: BL-030)
Todos los formularios de la app reciben los montos en pesos (COP, la moneda en que se guardan), aunque la vista se
muestre en otra moneda. Las pendientes siguen la misma regla (proponen el monto en pesos).

## 7. Revisión independiente
Ver la sección siguiente (agente `revisor`).
