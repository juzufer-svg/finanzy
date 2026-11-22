# UC-003 — Restablecer contraseña

- **REQ:** REQ-F-003
- **Actor principal:** Visitante
- **Disparador:** Pulsa «¿Olvidaste tu contraseña?»
- **Precondiciones:** —
- **Postcondiciones:** Contraseña nueva; cuenta activa; sesiones abiertas cerradas
- **Invariantes involucrados:** INV-007, INV-009, INV-010, INV-016

## Flujo principal
1. El visitante ingresa su correo.
2. El sistema responde siempre lo mismo y, si la cuenta existe, envía un código de restablecimiento.
3. El visitante ingresa el código y la contraseña nueva (≥ 8, confirmada).
4. El sistema cambia la contraseña, cierra todas las sesiones abiertas de la cuenta (en cualquier dispositivo)
   y lo invita a iniciar sesión.

## Flujos alternativos / excepciones
- 2a. Límite por destinatario alcanzado → no se envía, pero la respuesta es la misma.
- 4a. Código inválido → 400.

## Reglas de negocio
- El código de restablecimiento no sirve para verificar la cuenta y viceversa.

## Contrato asociado
`CONTRACTS/CT-001` · **BDD:** BDD-RECUPERACION
