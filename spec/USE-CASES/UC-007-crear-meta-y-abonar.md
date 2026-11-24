# UC-007 — Crear meta y abonar

- **REQ:** REQ-F-008, REQ-F-009
- **Actor principal:** Usuario
- **Disparador:** Pulsa «Nueva meta» o «Abonar»
- **Precondiciones:** Sesión activa
- **Postcondiciones:** Meta con su progreso; gasto registrado en «Ahorro»
- **Invariantes involucrados:** INV-001, INV-003, INV-008

## Flujo principal
1. El usuario crea una meta con nombre, objetivo y fecha.
2. El usuario abona un monto a la meta.
3. El sistema registra un gasto en «Ahorro» y suma el monto a la meta (WF-002).

## Flujos alternativos / excepciones
- 2a. Meta inexistente o ajena → 404 y no se registra ningún gasto.
- 3a. Falla la actualización de la meta → se revierte el gasto (500).
- 2b. (CHG-019, fase c) El abono puede indicar una cuenta de origen (UC-016): sin saldo suficiente → 409 y no se registra el gasto ni se suma a la meta (INV-008, INV-052).

## Reglas de negocio
- La meta está completada cuando lo ahorrado ≥ objetivo.

## Contrato asociado
`CONTRACTS/CT-006` · **BDD:** BDD-METAS
