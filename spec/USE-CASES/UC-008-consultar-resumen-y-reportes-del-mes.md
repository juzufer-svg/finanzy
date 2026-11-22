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

## Flujos alternativos / excepciones
- 2a. Falla la carga → mensaje de error con «Reintentar».

## Reglas de negocio
- El gasto diario promedio divide entre 30 (pregunta abierta 2).

## Contrato asociado
`CONTRACTS/CT-003` · **BDD:** BDD-TRANSACCIONES
