# UC-009 — Cambiar moneda de visualización

- **REQ:** REQ-F-011
- **Actor principal:** Usuario
- **Disparador:** Elige una moneda en «Perfil»
- **Precondiciones:** Sesión activa
- **Postcondiciones:** Montos mostrados en la moneda elegida
- **Invariantes involucrados:** —

## Flujo principal
1. El usuario elige la moneda.
2. El sistema la guarda en el navegador y en su perfil.
3. Los montos se convierten desde COP.

## Flujos alternativos / excepciones
- 2a. El servidor falla → la preferencia queda guardada en el navegador.

## Reglas de negocio
- —

## Contrato asociado
`CONTRACTS/CT-002` · **BDD:** —
