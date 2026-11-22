# WF-001 — Registro y verificación por correo

- **REQ / UC:** REQ-F-001 · UC-001
- **Disparador:** `POST /auth/register`

| Paso | Actor/Sistema | Acción | Decisión / condición | Si falla (compensación) |
|---|---|---|---|---|
| 1 | Backend | Aplicar límite por IP (10/hora) | Superado → 429 | — |
| 2 | Backend | Buscar el correo | Activa → 409; pendiente → ir a 4 | — |
| 3 | Backend | Crear cuenta pendiente (hash bcrypt) | — | Error de BD → 500 (no se guarda nada) |
| 4 | Backend | `_issue_code`: ¿código de < 60 s? ¿límite diario/global? | Reciente → no reenvía; límite → 429 | — |
| 5 | Backend (tarea en segundo plano) | Enviar correo por Brevo | Error de Brevo → se registra en logs | El usuario puede pedir «Reenviar código» |
| 6 | Visitante | `POST /auth/verify-email` | Código inválido → 400 | Pedir otro código |
| 7 | Backend | Activar cuenta y emitir sesión | — | — |
| 8 | Sistema (cada 10 min) | Eliminar cuentas pendientes con > 1 hora | — | — |

**Dependencias externas:** Brevo. **Idempotencia:** repetir el registro dentro de 60 s no envía otro correo.
**Timeouts/reintentos:** 15 s hacia Brevo, sin reintento automático.
