# UC-005 — Gestionar categorías

- **REQ:** REQ-F-006
- **Actor principal:** Usuario
- **Disparador:** Abre «Crear categorías»
- **Precondiciones:** Sesión activa
- **Postcondiciones:** Categorías propias actualizadas
- **Invariantes involucrados:** INV-001, INV-004

## Flujo principal
1. El sistema muestra las categorías del usuario (crea las 7 por defecto si no tiene).
2. El usuario crea, edita o elimina una categoría.
3. El sistema guarda el cambio.

## Flujos alternativos / excepciones
- 3a. Eliminar: se pide confirmación; sus transacciones quedan sin categoría y sus presupuestos se eliminan.

## Reglas de negocio
- —

## Contrato asociado
`CONTRACTS/CT-004` · **BDD:** BDD-PROPIEDAD
