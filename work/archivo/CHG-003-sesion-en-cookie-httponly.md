# CHG-003 — Sesión en cookie HttpOnly (sin token en el navegador)

- **Estado:** aprobado y fusionado (PR #6, 2026-11-22)
- **Fecha:** 2026-11-22 · **Solicitante:** dueño del proyecto · **Riesgo:** alto (sesión, seguridad) · modo `completo`

## 1. Pedido original
> si implementa lo que consideres correcto implementar para mi app sin dañar nada pero agregando seguridad a mi app.
(Prioridad 1 del brief de seguridad: cookies HttpOnly, BL-012.)

## 2. Diseño
Ver ADR-005. Proxy `frontend/app/api/v1/[...path]/route.ts` (reemplaza el `rewrite`), cookie
`__Host-finanzy_session` HttpOnly/Secure/SameSite=Lax, encabezado CSRF `x-finanzy-csrf`, rutas propias
`auth/logout` y `auth/adopt` (migración de sesiones antiguas sin cerrar la sesión a nadie). Backend sin cambios.

## 3. Usos del token antes del cambio (todos migrados)
`store/auth.ts` (localStorage + cookie legible), `lib/api-client.ts` (Authorization desde localStorage),
`app/auth/login/page.tsx` y `app/auth/register/page.tsx` (`setToken` + `document.cookie`), y la comprobación
`localStorage.getItem('token')` en `dashboard/page.tsx`, `goals`, `transactions`, `budgets`, `reports`.
`grep -rn "localStorage.getItem('token')\|access_token\|setToken" frontend/app frontend/store` → solo la migración.

## 4. Evidencia
- `npx eslint .` 0 problemas · `npx next build` correcto · backend: 94 pruebas (sin cambios en backend).
- Prueba de punta a punta (`frontend/e2e/sesion-cookie.mjs`, Playwright, backend local con usuarios en memoria):
  12/12 ✔ — migración de sesión antigua, login sin token en la respuesta, JavaScript no ve el token, CSRF → 403,
  perfil con cookie, logout borra la cookie, dashboard sin sesión → login, sin errores de JavaScript.
- Con `curl`: Origin ajeno → 403; Authorization enviado por el navegador se ignora → 401; ruta con `..` → 400;
  login con contraseña mala muestra «Credenciales inválidas» sin recargar.
- No probado de punta a punta: registro y recuperación con correo real (usan las mismas rutas del proxy que el login;
  `verify-email` comparte el código que guarda la cookie).

## 4b. Revisión independiente (ciclo 1 → cambios requeridos, corregidos)
- Migración podía pisar o borrar una sesión recién iniciada (token viejo en localStorage) → `adopt` no toca una
  cookie existente; `setUser` (login/verificación) borra el token viejo. Probado: cookie + adopt vencido → 204 y la
  sesión sigue; e2e con token vencido antes del login → la sesión nueva sigue (13/13 ✔).
- `adopt` con backend caído daba 500 y el navegador borraba el token → 502 y el token se conserva para reintentar.
- Un 401 del login (contraseña mala) borraba la cookie → solo se borra en rutas que no son `auth/*`.
- `logout()` se espera antes de navegar. XFF/cabeceras: documentado en ADR-005 y CT-001.

## 5. Despliegue
- Sin cambios de variables: Vercel ya tiene `BACKEND_URL`. Sin SQL. Backend sin cambios.
- Tras desplegar: probar el bloqueo de login (5 intentos) desde el celular con datos y desde el wifi: solo debe
  bloquearse ese correo, no la app entera (comprueba que Railway ve la IP real). Entrar a la app; la sesión abierta debe seguir abierta. En el navegador (F12 → Application →
  Cookies) debe verse `__Host-finanzy_session` con HttpOnly ✓ y en Local Storage ya no debe existir `token`.
- Actualizar `CONTEXTO_PROYECTO_CLAUDE.md` §4 (frontend: `api-client.ts`, `store/auth.ts`, proxy) y §8 (sesión).
