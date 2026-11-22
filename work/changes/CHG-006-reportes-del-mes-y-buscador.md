# CHG-006 — Reportes del mes (proyección, promedio real, vs mes anterior, gráfico) y buscador

- **Estado:** listo-para-aprobar
- **Fecha:** 2026-11-22 · **Solicitante:** dueño del proyecto · **Riesgo:** bajo (solo frontend, sin cambios de API ni BD)
  · modo `completo` por mostrar cálculos de dinero

## 1. Pedido original (literal)
> Proyección de cómo cierras el mes y promedio diario real. Hoy Reportes divide siempre entre 30.
> 4. Comparación con el mes anterior, en el total y por categoría.
> 5. Gráfico del gasto acumulado día a día con la línea del presupuesto.
> 6. Buscador y filtro por categoría en Transacciones.

## 2. Decisiones
- **Promedio diario** = gastos ÷ días transcurridos (mes cerrado: días reales; mes en curso: hasta hoy; futuro: "—").
  Resuelve la pregunta abierta 2 / BL-007 con lo que pidió el dueño.
- **Proyección** solo para el mes en curso; se compara con el **presupuesto total** = suma de los presupuestos de
  categorías de gasto del mes (Finanzy no tiene un presupuesto global; se reutiliza `GET /presupuestos/{mes}`).
- **Comparación** con el mes anterior: tarjetas del tablero (`DashboardSummary`, una llamada extra a
  `resumen/{mes-1}`; si falla, solo se omite la comparación) y en Reportes, total y tabla por categoría.
- **Gráfico** SVG propio (`components/SpendingChart.tsx`), sin librerías: mes elegido (azul), mes anterior (gris,
  contexto) y presupuesto (punteado). Leyenda + etiqueta directa del presupuesto, tooltip con el puntero y con las
  flechas del teclado, `aria-label` con el resumen. Colores validados (contraste ≥ 3:1 en claro y oscuro).
- **Reportes**: primero una frase con la conclusión ("Te pasaste…", "Al ritmo actual cerrarías…"). Se quitaron la
  tarjeta "Mayor categoría" (ahora es el subtítulo) y la barra "Distribución de gastos vs ingresos" (siempre
  mostraba ingresos al 100 %); el "Resumen del período" quedó en la tarjeta Balance.
- **Buscador**: texto en descripción o nombre de categoría, sin tildes ni mayúsculas, + filtro por categoría
  (incluida "Sin categoría"). Con filtro activo los grupos se abren solos. Las transacciones "Sin categoría" ahora
  tienen editar y eliminar (antes no se podían corregir).
- Cálculos puros en `frontend/lib/month-stats.ts`, probados con `node --test` (`npm test`), sin dependencias nuevas;
  se agregó al CI.

## 3. Spec afectada
REQ-F-005 (CA-4, CA-5), REQ-F-010 (CA-2..5), UC-008, BDD-TRANSACCIONES, pregunta abierta 2 (resuelta), BL-007, BL-010.

## 4. Evidencia
`npm test` → 11 pruebas pasan · `npx eslint .` 0 problemas · `npx next build` correcto · revisión visual en el
navegador con datos de prueba (claro y oscuro, escritorio y celular).
