# CHG-016 — La moneda elegida se aplica al entrar

- **Modo:** ligero (solo presentación; no cambia API, datos ni reglas de negocio). **Estado:** en revisión del dueño.
- **Requerimiento:** REQ-F-011 (CA-4 nuevo) · BL-034.

## Problema
Un usuario eligió pesos (COP) y cada vez que entraba veía dólares; en Perfil ya aparecía COP marcado y había que volver a tocarlo.
Causa: la preferencia guardada en el servidor (`users.currency`, por defecto USD) solo se leía en Perfil y únicamente si el navegador no
tenía ya un valor guardado. El panel arrancaba con lo del navegador o con USD.

## Decisión
La cuenta manda: `dashboard/layout.tsx` lee `GET /api/v1/users/me` al entrar y aplica la moneda antes de mostrar montos (pantalla de
carga breve para que no parpadee en dólares). Si no hay conexión se usa la del navegador. Perfil solo muestra los datos. Los cambios
siguen guardándose con `PUT /users/me/currency` (sin cambios de contrato).

## Archivos
`frontend/app/dashboard/layout.tsx`, `frontend/app/dashboard/profile/page.tsx`, `frontend/lib/currency.ts` (`isSupportedCurrency`),
`frontend/tests/currency.test.mjs`, `spec/REQUIREMENTS.md`, `spec/TRACEABILITY.md`, `work/BACKLOG.md`.

## Pruebas
- `npx eslint .` 0 problemas · `tsc --noEmit` ok · `npm test` 29/29 · `next build` ok.
- Playwright (cuenta con COP): navegador nuevo → Inicio `$95.000` al entrar; navegador con USD viejo → `$95.000` y se corrige el valor local.

## Pendiente
Despliegue (push a `main`) sujeto a aprobación del dueño. Sin cambios de variables de entorno ni SQL.
Nota: los usuarios que nunca guardaron moneda en el servidor siguen en USD (valor por defecto); deben elegirla una vez en Perfil.
