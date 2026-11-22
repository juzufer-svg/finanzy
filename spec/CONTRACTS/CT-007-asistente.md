# CT-007 — Asistente `/api/v1/asistente`

- **Versión:** v1 · **UC:** UC-011 · **REQ:** F-015 · **ADR:** ADR-006
- **Permiso requerido:** sesión vigente (INV-016; errores comunes 401/503 en CT-002).

| Endpoint | Entrada | Respuesta | Errores propios |
|---|---|---|---|
| `POST /asistente/chat` | `{ "pregunta": "1-500", "historial": [{ "rol": "usuario" \| "asistente", "texto": "1-2000" }] (0-10, opcional) }` | 200 `{ "respuesta": "texto", "modelo": "claude-haiku-5-5", "uso": { "input_tokens", "output_tokens" } }` | 422 entrada inválida; 429 límite por minuto, diario por usuario o global (INV-024); 503 sin `ANTHROPIC_API_KEY`, API de Claude ocupada, sin saldo o mal configurada; 502 la API de Claude no pudo responder |

## Comportamiento
1. Valida la sesión y, si no hay `ANTHROPIC_API_KEY`, responde 503 **sin** llamar a Claude ni consumir límites.
2. Aplica los límites (INV-024) y envía la pregunta + historial + herramientas a la API de Claude.
3. Claude pide herramientas de **solo lectura**; el backend las ejecuta con el `usuario_id` del token (INV-023):
   `resumen_mes`, `movimientos_principales`, `totales_por_categoria`, `totales_por_medio_pago`,
   `buscar_movimientos`, `metas_ahorro`. Una herramienta desconocida o con datos inválidos devuelve un error a Claude, no al usuario.
4. Como mucho 5 llamadas a Claude por pregunta; la última se hace sin herramientas para obligar a responder.
5. El historial se normaliza: se descartan mensajes del asistente al inicio y se unen dos seguidos del mismo rol.
6. La conversación no se guarda en la base de datos.
