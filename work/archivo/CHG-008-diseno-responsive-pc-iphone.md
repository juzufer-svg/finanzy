# CHG-008 — Diseño profesional en PC y iPhone

- **Estado:** listo-para-aprobar
- **Fecha:** 2026-11-22 · **Solicitante:** dueño del proyecto
- **Riesgo:** bajo (estilos, textos y accesibilidad; solo frontend) · modo `ligero`

## 1. Pedido original (literal, sin reinterpretar)
> necsito que tanto en el entorno web en pc como desde celular se vea bien todo el dashboard y diferentes menu. por jemeplo en modo web en compuatdro se ve dos veces el icono de finanzy como en la imagen entre otras cosas, la diea es que quede todo muy profesional asi como en el celular iphone se vea bien tambein.

## 2. Clasificación
Tipo: mejora visual / accesibilidad. Módulo: frontend (layout del dashboard, vistas, componentes). Riesgo bajo:
no toca API, datos, dinero, seguridad ni infraestructura. Requerimientos afectados: REQ-N-005 (accesibilidad) y la
presentación de REQ-F-004..010 (sin cambiar su comportamiento).

## 3. Análisis
- **Alcance:** layout del dashboard (barra lateral, barra superior, menú y barra inferior móviles), las 6 vistas,
  modales, avisos y viewport del iPhone.
- **Fuera de alcance:** reglas de negocio, contratos API, base de datos, páginas de autenticación (ya se veían bien;
  solo heredan el arreglo del logo y el viewport).
- **Problemas encontrados (con capturas antes/después):**
  1. Logo dos veces en PC (barra lateral y barra superior).
  2. En el celular el ícono del logo salía cortado (solo la flecha): ids `fGrad`/`chartGrad` repetidos y la copia
     de la barra lateral oculta con `display:none` invalidaba el degradado. Ahora cada instancia usa `useId()`.
  3. "Noviembre De 2026" (clase `capitalize`): ahora `monthTitle()` → "Noviembre de 2026".
  4. Botones editar/eliminar que solo aparecían al pasar el mouse: invisibles en iPhone. Ahora `reveal-on-hover`
     (con mouse, al pasar; en táctil, siempre visibles).
  5. Campos de 14 px: Safari en iPhone hacía zoom al escribir. Ahora 16 px en pantallas pequeñas.
  6. Sin `viewport-fit=cover` ni márgenes seguros: barra inferior pegada a la barra de inicio del iPhone.
  7. La página se desplazaba en un contenedor interno (`h-screen` + `overflow-auto`): Safari no ocultaba sus barras.
  8. Tarjetas de resumen en 3 columnas en el celular con montos cortados ("$40.000.0…").
  9. Barra inferior con 6 botones y textos de 9 px cortados; ahora 5 (Perfil se abre desde el avatar).
  10. Encabezados y botones de mes distintos en cada vista; ahora `PageHeader` + `MonthNavigator`.
  11. Avisos (toasts) tapaban la barra inferior; el perfil tenía su propio aviso (ahora usa `notify()`).
  12. Botones solo con ícono sin nombre accesible; enlaces sin `aria-current`; plurales ("1 completadas").
- **Decisiones de diseño (sin cambiar reglas):** botón de modo claro/oscuro en la barra superior (antes solo en
  Perfil); el botón "Crear Categorías" de Transacciones pasa a "Categorías" con el estilo secundario común
  (abre el mismo administrador); meta al 100 % muestra "¡Meta cumplida!" en lugar de "Fecha vencida"; fechas de listas "5 nov".

## 4. Preguntas abiertas
| # | Pregunta | Impacto | Respuesta | Quién |
|---|---|---|---|---|
| 1 | ¿Se mantiene "Dashboard" como nombre del menú? | Bajo | Se mantuvo (no se renombraron menús) | Agente |

## 5. Spec afectada
- REQ: REQ-N-005 (accesibilidad) · Sin cambios en UC, estados, invariantes, contratos, BDD ni ADR.
- **Aprobación de la spec:** no aplica (modo ligero, sin cambio de comportamiento).

## 6. Implementación
- Nuevos: `frontend/components/PageHeader.tsx`, `frontend/components/MonthNavigator.tsx`.
- `frontend/lib/month-stats.ts`: `monthTitle()`, `shortDate()` (+ pruebas en `frontend/tests/month-stats.test.mjs`).
- `frontend/app/dashboard/layout.tsx`, `frontend/app/layout.tsx` (viewport), `frontend/app/globals.css`,
  `frontend/components/FinanzyLogo.tsx`, `DashboardSummary.tsx`, `TransactionList.tsx`, `BudgetCard.tsx`,
  `GoalProgressCard.tsx`, `DialogProvider.tsx` y las 6 vistas de `frontend/app/dashboard/`.

## 7. Validación
- `npx eslint .` → 0 problemas · `npm test` → 16/16 · `npx next build` → correcto.
- Capturas antes/después en 1440 px (claro y oscuro) e iPhone 13 (claro y oscuro), con datos de prueba.
- Revisión independiente: ver la sección 8.

## 8. Revisión
Revisor independiente (2026-11-22): **APROBADO CON OBSERVACIONES**, nada bloqueante. Corregido en este mismo cambio:
nombre accesible del avatar con el texto visible (WCAG 2.5.3), alto con `100dvh` mediante `.min-h-viewport`, clase
sin efecto en la barra superior, comentario de `shiftMonth`, menú móvil sin `aria-modal` (no atrapa el foco),
16 px para todo campo en el celular, Reportes usa `monthTitle()`, nota del botón "Categorías".
Nota de alcance: `CONTEXTO_PROYECTO_CLAUDE.md` del repositorio se sincronizó con la copia viva del proyecto, que ya
registraba PR #5 a #9 (CHG-002 a CHG-007); por eso el diff incluye esas líneas.
Fuera de alcance (ya pasaba antes): tocar en el menú móvil la página actual no cierra el menú.
