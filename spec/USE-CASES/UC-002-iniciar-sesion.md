# UC-002 — Iniciar sesión

- **REQ:** REQ-F-002
- **Actor principal:** Visitante
- **Disparador:** Pulsa «Iniciar sesión»
- **Precondiciones:** —
- **Postcondiciones:** Sesión de 7 días guardada en el navegador
- **Invariantes involucrados:** INV-006, INV-010, INV-011, INV-015, INV-037 a INV-041 (CHG-020)

## Flujo principal
1. El visitante ingresa correo y contraseña.
2. El sistema valida las credenciales.
3. El sistema entrega la sesión y abre el dashboard.

## Flujos alternativos / excepciones
- 2a. Credenciales inválidas → 401; al 5.º fallo el correo se bloquea 15 min (429).
- 2b. Cuenta pendiente → no hay sesión; se envía código y se pide verificar (INV-006).
- 2c. (CHG-020) El bloqueo de 15 min y los límites por IP viven en PostgreSQL y **no se pierden con un despliegue** (INV-037); 50 intentos simultáneos no comprueban más de 5 contraseñas (INV-038).
- 2d. (CHG-020) Si la BD de estado falla o tarda más de 5 s → 503 «Servicio no disponible…»; nunca se concede sesión (INV-039, fail-closed).

## Reglas de negocio
- El correo se compara en minúsculas.

## Contrato asociado
`CONTRACTS/CT-001` · **BDD:** BDD-AUTH, BDD-AUTH-PERSISTENTE
