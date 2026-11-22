# UC-004 — Registrar transacción

- **REQ:** REQ-F-004
- **Actor principal:** Usuario
- **Disparador:** Completa el formulario «Nueva transacción»
- **Precondiciones:** Sesión activa
- **Postcondiciones:** Transacción guardada y lista actualizada
- **Invariantes involucrados:** INV-001, INV-002, INV-003, INV-004, INV-005

## Flujo principal
1. El usuario elige tipo, categoría, monto, fecha y descripción.
2. El sistema valida y guarda la transacción.
3. La lista y el resumen del mes se actualizan.

## Flujos alternativos / excepciones
- 2a. Datos inválidos → 422 con mensaje legible.
- 2b. Categoría ajena → 404.

## Reglas de negocio
- Editar y eliminar siguen las mismas reglas; eliminar pide confirmación.

## Contrato asociado
`CONTRACTS/CT-003` · **BDD:** BDD-TRANSACCIONES
