# CHG-009 — Filtro de período compartido y rediseñado

- **Estado:** listo-para-aprobar
- **Fecha:** 2026-11-22 · **Solicitante:** dueño del proyecto
- **Riesgo:** bajo (solo frontend: estado de la interfaz y diseño; sin API, datos ni seguridad) · modo `ligero`

## 1. Pedido original (literal, sin reinterpretar)
> me gustaria trabajar en un ajuste al filtro de fecha actualmente se ve muy veo, trata de re implementarlo y que se vea mejor y que cuando se coloque el filtro lo tomen todas las pestañas porque actualmente solo la toma dashboard y se quita si se carga otra pestaña  o menu, analiza bien y diseñalo profesionalemtne como lo ahria un ingeiero senior.

## 2. Clasificación
Tipo: mejora de interfaz y corrección de comportamiento de la interfaz. Módulo: frontend (Dashboard, Transacciones,
Presupuestos, Reportes). Riesgo bajo. REQ afectados en su presentación: REQ-F-005, REQ-F-007, REQ-F-010.

## 3. Análisis
- **Causa:** cada vista tenía su propio `useState` con el mes, que nace en el mes actual al montar la vista.
  Al cambiar de menú, la vista nueva se monta de cero y pierde el mes elegido.
- **Defecto adicional encontrado:** Presupuestos calculaba el mes con `new Date().toISOString().slice(0, 7)` (hora UTC):
  en Colombia (UTC-5), el último día del mes después de las 7 p. m. mostraba el mes siguiente.
- **Diseño elegido:**
  - `store/period.ts` (Zustand, ya es dependencia): un solo período `YYYY-MM` para todas las vistas.
  - Se guarda en `sessionStorage`: se mantiene al navegar y al recargar; una pestaña nueva arranca en el mes actual (con `localStorage` la app abriría semanas después en un mes viejo sin que se note).
    Se valida al leerlo (`isValidMonth`) y se borra al cerrar sesión o cuando la sesión vence.
  - `components/PeriodPicker.tsx` reemplaza a `MonthNavigator`: [‹] [📅 Noviembre de 2026 ▾] [›] + "Mes actual"
    (o "Hoy" en el celular) cuando no es el mes en curso. El botón central abre un calendario de meses con cambio
    de año; el mes actual lleva un punto. Accesible: `aria-expanded`, Esc, clic fuera, foco al mes elegido y
    vuelta al botón, flechas del teclado en la cuadrícula. En el celular ocupa todo el ancho.
  - Mientras llega el mes nuevo, cada vista marca los datos viejos (`stale`) en vez de mostrarlos como si fueran
    del mes nuevo; Reportes muestra el esqueleto de carga como antes.
- **Alternativa descartada:** `?mes=` en la URL. Sirve para compartir enlaces, pero obliga a que todos los enlaces
  del menú lo lleven y no aporta en una app personal. Se puede añadir después sobre el mismo store.
- **Fuera de alcance:** Metas y Perfil no dependen del mes. El formulario de nueva transacción sigue proponiendo la
  fecha de hoy aunque se esté viendo otro mes (pendiente de decisión del dueño).

## 4. Preguntas abiertas
| # | Pregunta | Impacto | Respuesta | Quién |
|---|---|---|---|---|
| 1 | ¿El período debe recordarse también al cerrar el navegador? | Bajo | Se eligió no (sessionStorage); fácil de cambiar | Agente |
| 2 | ¿La nueva transacción debe proponer una fecha del mes que se está viendo? | Bajo | Pendiente | Dueño |

## 5. Spec afectada
- REQ: presentación de REQ-F-005/007/010; REQ-N-005 (accesibilidad). Sin cambios en UC, invariantes, contratos ni ADR.

## 6. Implementación
- Nuevos: `frontend/store/period.ts`, `frontend/components/PeriodPicker.tsx`. Eliminado: `frontend/components/MonthNavigator.tsx`.
- `frontend/lib/month-stats.ts`: `isValidMonth()` (+ prueba). `frontend/components/PageHeader.tsx`: `wideActions`.
- Vistas: `frontend/app/dashboard/{page,transactions/page,budgets/page,reports/page}.tsx`; cierre de sesión en `layout.tsx`.

## 7. Validación
- `npx eslint .` → 0 · `npm test` → 17/17 · `npx next build` → correcto.
- Recorrido automatizado (Playwright, PC claro/oscuro e iPhone 13 claro/oscuro): elegir septiembre en Dashboard →
  Transacciones, Presupuestos y Reportes muestran septiembre → recargar mantiene septiembre → "Mes actual" vuelve a
  noviembre. 20/20 comprobaciones correctas.

## 8. Revisión
Revisor independiente (2026-11-22): **APROBADO CON OBSERVACIONES**, nada bloqueante. Corregido en este cambio: el foco
vuelve al selector tras "Mes actual"; salir del calendario con Tab lo cierra; las tarjetas de Transacciones se marcan
mientras carga el mes nuevo; el período también se borra cuando la sesión vence; textos del comentario; clase sin efecto.
