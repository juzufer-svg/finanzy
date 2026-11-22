# UC-008 — Consultar resumen y reportes del mes

- **REQ:** REQ-F-005, REQ-F-010
- **Actor principal:** Usuario
- **Disparador:** Abre el dashboard o «Reportes»
- **Precondiciones:** Sesión activa
- **Postcondiciones:** —
- **Invariantes involucrados:** INV-001, INV-005

## Flujo principal
1. El usuario elige el mes.
2. El sistema muestra ingresos, gastos, balance, transacciones por categoría y reportes.
3. En Reportes ve primero una frase con la conclusión del mes, los indicadores (con la variación frente al mes
   anterior), el gráfico del gasto acumulado y la tabla de gastos por categoría frente al mes anterior.
4. En Transacciones puede buscar por texto y filtrar por categoría.

## Flujos alternativos / excepciones
- 2a. Falla la carga → mensaje de error con «Reintentar».

## Reglas de negocio
- Gasto diario promedio = gastos ÷ días transcurridos: los días reales del mes si ya cerró, el día de hoy si es el
  mes en curso; si el mes no ha empezado se muestra "—" (CHG-006, resuelve la pregunta abierta 2).
- Proyección al cierre (solo mes en curso) = promedio diario × días del mes, nunca menor que lo ya anotado en el mes.
- En el mes en curso, los movimientos con fecha posterior a hoy (p. ej. un arriendo anotado para el día 30) sí suman
  en los totales del mes, pero no cuentan para el promedio, la proyección ni la comparación con el mes anterior, que
  se hace hasta el mismo día; la tarjeta de Gastos de Reportes indica cuánto está anotado a futuro.
- Presupuesto total del mes = suma de los límites de las categorías de gasto (`presupuestos/{mes}`).
- Variación = (actual − anterior) ÷ anterior × 100; sin valor anterior se muestra "Sin datos"/"Nueva".
- Los cálculos viven en `frontend/lib/month-stats.ts` y se prueban con `npm test`.

## Contrato asociado
`CONTRACTS/CT-003` · **BDD:** BDD-TRANSACCIONES
