# CHG-011 — «Asistente IA» y menú lateral que reaparecía en el celular

- **Estado:** listo-para-aprobar
- **Fecha:** 2026-11-22 · **Solicitante:** dueño del proyecto
- **Riesgo:** bajo (solo frontend: textos y estado de la interfaz; sin API, datos ni seguridad) · modo `ligero`

## 1. Pedido original (literal, sin reinterpretar)
> y necesito que en mi front  el menu de asistente diga Asistente IA y que cuando se le al icono del mensaje se abra pero en el modo cel o iphone no me meustre o los menu del panel izqueirdo actualmente se ve y toca cerrarlo.

## 2. Clasificación
Tipo: texto de la interfaz + corrección de un defecto de la interfaz. Módulo: frontend (`dashboard/layout.tsx`,
`dashboard/assistant/page.tsx`). Riesgo bajo. REQ afectados en su presentación: REQ-N-005 (UC-011 para el nombre).

## 3. Análisis
- **Causa del menú que reaparecía:** el menú lateral del celular guardaba la ruta donde se abrió
  (`mobileMenuPath`) y se mostraba siempre que la ruta actual coincidiera. Al salir de esa ruta por un enlace del
  menú, el valor quedaba guardado; al volver a ella (por ejemplo, con el ícono de chat de la barra superior hacia el
  asistente, o con Atrás/Adelante del navegador) el menú se abría solo y había que cerrarlo a mano.
  Reproducido con Playwright en iPhone 13: abrir el menú en el asistente → Transacciones → ícono de chat ⇒ menú visible.
- **Corrección:** `mobileMenuOpen` pasa a ser un booleano que se pone en `false` en cada cambio de ruta, ajustando el
  estado durante el render (patrón recomendado por React, sin efecto ni `setState` síncrono en efectos).
- **Nombre:** «Asistente» → «Asistente IA» en el menú lateral, el menú del celular, el título de la barra superior,
  el título de la página y el nombre accesible del ícono de chat (UC-011 actualizado).
- **Ajuste menor del flujo móvil:** el texto de ejemplo del campo de pregunta se cortaba en dos líneas en el celular;
  ahora dice «Escribe tu pregunta…» (las preguntas sugeridas ya dan los ejemplos).

## 4. Preguntas abiertas
Ninguna.

## 5. Spec afectada
`spec/USE-CASES/UC-011-preguntar-al-asistente.md` (nombre del menú) y `spec/TRACEABILITY.md` (REQ-N-005).
Sin cambios de contrato, reglas de negocio ni BD.

## 6. Evidencia
- Recorrido Playwright (iPhone 13 claro y oscuro): antes, el menú aparecía en los pasos «volver al asistente con el
  ícono» y «Adelante»; después, en ningún paso. PC: el título muestra «Asistente IA».
- Capturas: `/mnt/project-files/asistente-ia/iphone-antes-ahora.png`, `/mnt/project-files/asistente-ia/pc-asistente-ia.png`.
- ESLint 0 problemas, `npm test` 17/17, `next build` correcto.

## 7. Revisión independiente
Revisor: APROBADO CON OBSERVACIONES (confianza 90 %). Atendidas:
- Los enlaces del menú móvil también lo cierran al tocarlos (si se toca la página en la que ya se está, la ruta no cambia).
- El cambio del texto del campo de pregunta queda documentado en §3 como ajuste menor del flujo móvil.
- BL-021 (Hecho, PR #11) y BL-022 (descartado por el dueño) se anotan también en CHG-009.
