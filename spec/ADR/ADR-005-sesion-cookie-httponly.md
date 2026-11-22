# ADR-005 — Sesión en cookie HttpOnly con proxy de Next.js

- **Estado:** aceptada
- **Fecha:** 2026-11-22 · **Decide:** dueño del proyecto (delegó: «lo que consideres correcto»; CHG-003)

## Contexto
El JWT se guardaba en `localStorage` y en una cookie legible por JavaScript. Cualquier XSS (la CSP permite
`'unsafe-inline'` en scripts) podía robar el token y usarlo desde otro equipo durante 7 días. REQ-N-001, REQ-N-003.

## Alternativas evaluadas
| Opción | Pros | Contras |
|---|---|---|
| Seguir con `localStorage` | Sin cambios | El token es robable por XSS |
| Cookie HttpOnly emitida por el backend (Railway) | Sin capa extra | Railway y Vercel son dominios distintos: cookie de terceros, bloqueada por Safari/Chrome |
| **Proxy en Next.js (Route Handler) que guarda el JWT en cookie HttpOnly** | Cookie del mismo sitio; backend sin cambios; el navegador nunca ve el token | Una función de Vercel por petición (plan gratis suficiente) |

## Decisión
- `app/api/v1/[...path]/route.ts` reemplaza el `rewrite` de `next.config.js`. Al iniciar sesión (`login`,
  `verify-email`) quita `access_token` y `token_type` de la respuesta y guarda el JWT en la cookie
  `__Host-finanzy_session` (HttpOnly, Secure, SameSite=Lax, Path=/, duración = `exp` del JWT).
- En cada petición convierte la cookie en `Authorization: Bearer` hacia el backend; ignora el Authorization que
  envíe el navegador. Sin cookie, las rutas protegidas responden 401 sin llamar al backend.
- **CSRF:** las peticiones que cambian datos exigen el encabezado `x-finanzy-csrf: 1` y, si traen `Origin`, debe
  ser el mismo host. Junto con SameSite=Lax, un sitio ajeno no puede usar la sesión.
- `POST /api/v1/auth/logout` borra la cookie. Un 401 del backend también la borra (un 503 no, INV-016).
- **Migración sin cerrar sesiones:** si el navegador tiene el token antiguo en `localStorage`, `apiClient` lo envía
  una sola vez a `POST /api/v1/auth/adopt`, que lo valida con `GET /users/me` y lo pasa a la cookie; luego se borra.
  `adopt` nunca reemplaza una cookie existente, iniciar sesión borra el token antiguo, y ante un fallo pasajero del
  backend (5xx o sin red) el token se conserva y se reintenta (INV-016).
- El navegador solo guarda `user` (id, correo, nombre) para pintar la interfaz.

## Consecuencias
- Positivas: un XSS ya no puede leer ni exfiltrar el token. Backend sin cambios (sigue aceptando Bearer).
- Negativas / deuda aceptada: cerrar sesión borra la cookie pero el JWT sigue siendo válido hasta su `exp` si alguien
  lo copió antes (ya no es posible desde JavaScript). Un XSS aún podría hacer peticiones desde la misma página
  mientras esté abierta (mitigado por la CSP).
- Impacto: CT-001 (respuestas de sesión en el navegador), INV-020, `frontend/lib/api-client.ts`, `store/auth.ts`,
  páginas de login/registro/dashboard, `next.config.js`. Variable `BACKEND_URL` de Vercel sigue siendo la misma.
