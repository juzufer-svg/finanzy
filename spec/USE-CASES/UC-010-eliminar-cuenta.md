# UC-010 — Eliminar cuenta

- **REQ:** REQ-F-013
- **Actor principal:** Usuario
- **Disparador:** Pulsa «Eliminar cuenta» en «Perfil»
- **Precondiciones:** Sesión activa
- **Postcondiciones:** Cuenta y datos eliminados; sesión cerrada
- **Invariantes involucrados:** INV-001

## Flujo principal
1. El usuario escribe su correo para confirmar.
2. El sistema elimina la cuenta y todos sus datos.
3. Se cierra la sesión.

## Flujos alternativos / excepciones
- 1a. El correo escrito no coincide → el botón sigue deshabilitado.

## Reglas de negocio
- Irreversible.

## Contrato asociado
`CONTRACTS/CT-002` · **BDD:** —
