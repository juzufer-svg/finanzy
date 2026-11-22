# CHG-007 — Medio de pago en las transacciones

- **Estado:** listo-para-aprobar
- **Fecha:** 2026-11-22 · **Solicitante:** dueño del proyecto · **Riesgo:** medio (BD + contrato API) · modo `completo`

## 1. Pedido original (literal)
> agregar los metodos de pago efectivo, debito y demas realizar todos los cambios includios en la abse de datos los
> campos o tablas que hagan falta

Con la captura del artifact de referencia: Débito, Crédito, Efectivo, Transferencia, Nequi / Daviplata.

## 2. Decisiones
- **Columna, no tabla:** `transacciones.medio_pago varchar(20)` con CHECK de 5 códigos. Una tabla de medios por usuario
  (con alta/baja) es más de lo pedido; si más adelante se quieren medios propios (p. ej. "Tarjeta Visa"), se migra.
- **Opcional (NULL):** las transacciones antiguas y los abonos a metas (incluida la función `abonar_meta` del otro
  cambio en curso, que inserta columnas explícitas) siguen funcionando sin cambios. El formulario propone "Débito".
- **Códigos sin tildes** en la BD/API (`debito`, `nequi_daviplata`); los nombres se muestran en la interfaz
  (`frontend/lib/payment-methods.ts`), en el mismo orden que `MEDIOS_PAGO` del backend.
- **PUT:** si no se envía `medio_pago`, se conserva (clientes antiguos no lo borran); `null` lo quita.
- **Backend:** si no hay medio, el `insert` no envía la columna (si el backend se desplegara antes del SQL, crear sin
  medio seguiría funcionando; aun así, **el SQL va antes del despliegue**).
- **Interfaz:** selector en "Nueva transacción" y en "Editar"; el medio aparece junto a la fecha en las listas;
  filtro por medio en Transacciones; tarjeta "Gastos por medio de pago" en Reportes.

## 3. Spec afectada
REQ-F-004 (CA-4) · UC-004 · CT-003 v1.1 · INV-022 (nuevo) · BDD-TRANSACCIONES · BL-018.

## 4. Evidencia
- `python -m pytest -q` → todas pasan (111), 17 nuevas en `tests/test_medio_pago.py` (5 medios válidos, 5 inválidos, sin
  medio, editar conserva/cambia/quita, abono sin medio, columnas enviadas a Supabase).
- `backend/sql/pruebas/probar.sh`: la migración se puede repetir y el CHECK rechaza valores no permitidos.
- `npm test` (gasto por medio) · `npx eslint .` 0 problemas · `npx next build` correcto · revisión en el navegador.

## 5. Despliegue
1. Supabase → SQL Editor → ejecutar `backend/sql/2026-11-22_medio_pago.sql`. 2. Fusionar el PR (push a `main`).
No hay variables de entorno nuevas.

## Revisión independiente
Agente `revisor` (2026-11-22): aprobado con observaciones. Corregido (ya existía antes): editar con `categoria_id` vacío
enviaba `""` a una columna uuid (error 500); ahora queda sin categoría, como al crear
(`test_supabase_update_categoria_vacia_queda_sin_categoria`). Por decidir con el dueño: Débito preseleccionado.
