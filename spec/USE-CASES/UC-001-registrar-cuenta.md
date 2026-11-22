# UC-001 — Registrar cuenta

- **REQ:** REQ-F-001
- **Actor principal:** Visitante
- **Disparador:** Pulsa «Registrarse»
- **Precondiciones:** El correo no pertenece a una cuenta activa
- **Postcondiciones:** Cuenta activa y sesión iniciada
- **Invariantes involucrados:** INV-007, INV-010, INV-014

## Flujo principal
1. El visitante ingresa nombre, correo y contraseña.
2. El sistema crea la cuenta pendiente y envía un código de 6 dígitos (WF-001).
3. El visitante ingresa el código.
4. El sistema activa la cuenta e inicia la sesión.

## Flujos alternativos / excepciones
- 2a. Correo de cuenta activa → 409 «El correo ya está registrado».
- 2b. Ya se envió un código hace < 60 s → no se reenvía; el anterior sigue valiendo.
- 2c. Límite por IP o por destinatario → 429.
- 4a. Código incorrecto, vencido o invalidado → 400 «Código inválido o expirado».

## Reglas de negocio
- Las cuentas pendientes se eliminan tras 1 hora.

## Contrato asociado
`CONTRACTS/CT-001` · **BDD:** BDD-AUTH
