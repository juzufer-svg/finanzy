# ADR-006 — Asistente con la API de Claude (tool use)

- **Estado:** propuesta (requiere el visto bueno del dueño: implica un costo por uso)
- **Fecha:** 2026-11-22 · **Decide:** dueño del proyecto

## Contexto
El dueño quiere preguntar en lenguaje natural por sus finanzas ("¿cuáles fueron mis gastos más altos del mes?")
desde un chat dentro de Finanzy (REQ-F-015).

## Alternativas evaluadas
| Opción | Pros | Contras |
|---|---|---|
| Enviar todas las transacciones del mes en el prompt | Simple | Más tokens (costo), escala mal, más datos expuestos al modelo |
| Claude genera SQL y el backend lo ejecuta | Flexible | Riesgo alto: inyección, acceso a datos ajenos, escrituras |
| **Tool use con herramientas fijas de solo lectura** | Barato, seguro (el `usuario_id` sale del token), respuestas con datos exactos | Solo responde lo que cubren las herramientas |

## Decisión
Tool use. El backend (FastAPI) llama a `POST https://api.anthropic.com/v1/messages` con `httpx` (ya era dependencia:
sin librerías nuevas). Modelo configurable con `ANTHROPIC_MODEL`, por defecto **Claude Haiku** (`claude-haiku-5-5`),
el más económico. Clave `ANTHROPIC_API_KEY` solo en Railway.

## Consecuencias
- **Costo por uso** (no es gratis, regla 11 de `CLAUDE.md`): se cobra por tokens desde el saldo prepagado de la
  Claude Console. Topes (INV-024): 5 preguntas/min y `ASISTENTE_PREGUNTAS_POR_USUARIO_DIA` (30) por usuario al día,
  `ASISTENTE_PREGUNTAS_TOTALES_DIA` (300) en total al día, `max_tokens` 1024 y máximo 5 llamadas por pregunta.
  Además conviene fijar un límite de gasto mensual en la Claude Console.
- Los límites viven en memoria (se reinician con cada despliegue), igual que los de correo (ver BL-014).
- Los datos consultados (montos, descripciones y categorías del usuario) se envían a la API de Anthropic para
  generar la respuesta; nunca el correo, la contraseña ni el id del usuario.
- Sin `ANTHROPIC_API_KEY` el asistente responde 503 y el resto de la app sigue igual.
