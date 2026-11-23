# CHG-013 — Montos en la moneda elegida, sin duplicados y limpieza de código

- **Estado:** aprobado por el dueño (2026-11-23: «cuando realices eso apruebo de una vez todos los cambios en main»)
- **Riesgo:** medio (datos: fusiona duplicados con respaldo) · modo `completo`

## 1. Pedido original
> Si necesito que se muestre el monto de acuerdo a lo moneda que se elige y elimina código basura que no se esté
> utilizando la app debe quedar limpia de código basura o inutiluzable. Y si agrega una restricción para no duplicar nada.

## 2. Decisiones
- **Moneda (BL-030):** los formularios (transacciones, presupuestos, metas, abonos, recurrentes y pendientes) muestran
  y reciben el monto en la moneda elegida con su símbolo, y lo guardan convertido a COP (2 decimales). Al editar sin
  tocar el monto se conserva el valor exacto (evita que 85.000 → US$23,44 → 84.993 cambie solo). La API no cambia.
- **Sin duplicados (BL-031):** categorías (misma persona, nombre y tipo) y presupuestos (misma persona, categoría y mes).
  Índice UNIQUE con el nombre exacto para no romper `abonar_meta` (busca «Ahorro» exacto); la API además compara sin
  mayúsculas ni espacios. Los duplicados existentes se fusionan: se conserva la categoría más antigua (sus transacciones,
  presupuestos y recurrentes pasan a ella) y el presupuesto de mayor límite; lo borrado queda en `respaldo.*`.
  Las transacciones y recurrentes repetidas son válidas (dos cafés el mismo día) y no se restringen.
- **Limpieza:** `ejemplo.md`, 6 clases CSS sin uso (`card-hover`, `stat-card`, `text-gradient`, `badge-blue`,
  `section-title`, `page-header`), imports sin uso (`typing.List`, `verify_password` en `models/user.py`), el método
  `DemoTransaccionDB.obtener_resumen` (nadie lo llamaba) y la constante `FRECUENCIAS` del backend. Análisis con un
  script de referencias (frontend: ningún archivo sin usar) y `pyflakes` (backend: 0 avisos).
- Las categorías por defecto: si dos primeras cargas llegan a la vez, se relee lo guardado (antes podía devolver ids falsos).

## 3. Evidencia
- Backend `pytest` todo en verde (incluye `tests/test_sin_duplicados.py`); `pyflakes` sin avisos.
- SQL `probar.sh`: «OK: duplicados fusionados con respaldo y restricciones activas» (migración ejecutada dos veces).
- Frontend: eslint 0, `npm test` 28/28 (`tests/currency.test.mjs` nuevo), build correcto.
- Playwright: US$10 se guardan como $36.260 COP; pendientes y presupuestos se muestran en US$; guardar sin tocar el
  límite lo deja exacto.
