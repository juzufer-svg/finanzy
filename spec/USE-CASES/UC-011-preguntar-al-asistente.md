# UC-011 — Preguntar al asistente

- **REQ:** REQ-F-015 · **Contrato:** CT-007 · **ADR:** ADR-006
- **Actor principal:** Usuario
- **Disparador:** Abre «Asistente IA» (menú lateral o ícono de chat de la barra superior) y escribe una pregunta
- **Precondiciones:** Sesión activa; `ANTHROPIC_API_KEY` configurada en el backend
- **Postcondiciones:** Ninguna sobre los datos (solo lectura). La conversación no se guarda
- **Invariantes involucrados:** INV-001, INV-023, INV-024

## Flujo principal
1. El usuario escribe una pregunta (o toca una sugerencia que usa el mes elegido en el selector de período).
2. El sistema envía la pregunta y las últimas preguntas y respuestas a Claude con las herramientas de solo lectura.
3. Claude consulta las herramientas que necesita; el backend las responde con los datos del usuario del token.
4. El sistema muestra la respuesta y el consumo de tokens de esa respuesta.
5. El usuario puede seguir preguntando ("¿y el mes pasado?") o empezar una conversación nueva.

## Flujos alternativos / excepciones
- 2a. Sin clave configurada → "El asistente no está disponible…" (503).
- 2b. Se superó un tope → aviso de límite (429); la pregunta vuelve al campo.
- 3a. La API de Claude está ocupada, sin saldo o falla → aviso y la pregunta vuelve al campo para reintentar.
- 3b. Piden registrar o borrar algo → el asistente explica que eso se hace en la app.
