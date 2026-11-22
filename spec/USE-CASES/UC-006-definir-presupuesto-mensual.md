# UC-006 — Definir presupuesto mensual

- **REQ:** REQ-F-007
- **Actor principal:** Usuario
- **Disparador:** Pulsa «Nuevo presupuesto»
- **Precondiciones:** Sesión activa; categoría propia
- **Postcondiciones:** Presupuesto visible con su avance
- **Invariantes involucrados:** INV-001, INV-002, INV-003, INV-005

## Flujo principal
1. El usuario elige categoría y límite para el mes.
2. El sistema guarda el presupuesto.
3. Se muestra lo gastado y el avance (aviso ≥ 75 %, excedido ≥ 100 %).

## Flujos alternativos / excepciones
- 2a. Categoría ajena → 404.
- 2b. Límite ≤ 0 → 422.

## Reglas de negocio
- —

## Contrato asociado
`CONTRACTS/CT-005` · **BDD:** BDD-PROPIEDAD
