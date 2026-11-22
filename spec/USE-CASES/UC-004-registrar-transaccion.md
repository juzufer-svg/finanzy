# UC-004 — Registrar transacción

- **REQ:** REQ-F-004
- **Actor principal:** Usuario
- **Disparador:** Completa el formulario «Nueva transacción»
- **Precondiciones:** Sesión activa
- **Postcondiciones:** Transacción guardada y lista actualizada
- **Invariantes involucrados:** INV-001, INV-002, INV-003, INV-004, INV-005, INV-022

## Flujo principal
1. El usuario elige tipo, categoría, medio de pago (por defecto Débito; puede dejarlo «Sin especificar»), monto,
   fecha y descripción.
2. El sistema valida y guarda la transacción.
3. La lista y el resumen del mes se actualizan.

## Flujos alternativos / excepciones
- 2a. Datos inválidos → 422 con mensaje legible.
- 2b. Categoría ajena → 404.

## Reglas de negocio
- Editar y eliminar siguen las mismas reglas; eliminar pide confirmación.
- Medios de pago (INV-022): Débito, Crédito, Efectivo, Transferencia, Nequi / Daviplata, o sin especificar.
  Los abonos a metas y las transacciones anteriores a CHG-007 quedan sin especificar.

## Contrato asociado
`CONTRACTS/CT-003` · **BDD:** BDD-TRANSACCIONES
