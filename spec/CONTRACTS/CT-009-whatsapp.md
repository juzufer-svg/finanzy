# CT-009 — WhatsApp `/api/v1/whatsapp`

- **Versión:** v1 (CHG-014) · **UC:** UC-013 · **REQ:** F-017 · **ADR:** ADR-007 · **INV:** INV-029, INV-030

## Webhook de Meta (sin sesión; lo llama Meta directamente al backend)
| Endpoint | Entrada | Respuesta |
|---|---|---|
| `GET /whatsapp/webhook` | `hub.mode=subscribe`, `hub.verify_token`, `hub.challenge` | 200 texto plano = `hub.challenge` si el token coincide con `WHATSAPP_VERIFY_TOKEN`; si no, 403 |
| `POST /whatsapp/webhook` | Cuerpo de Meta + cabecera `X-Hub-Signature-256: sha256=<HMAC-SHA256(cuerpo, WHATSAPP_APP_SECRET)>` | 403 «Firma inválida» si falta o no coincide (o no hay App Secret). Si es válida, 200 `{"ok": true}` de inmediato y los mensajes se procesan en segundo plano |

Procesamiento de cada mensaje de texto (en orden):
1. Si el id del mensaje ya se procesó → se ignora (Meta reintenta).
2. Si el texto es un código `FZ-NNNNNN` (5 intentos/hora por número) → si es válido y vigente, enlaza el número a la
   cuenta que lo generó y responde «✅ ¡Listo!»; si no, responde que no es válido.
3. Si el número no está enlazado → se ignora sin responder ni llamar a la IA.
4. Mensajes que no son texto → responde que solo entiende texto (sin IA).
5. Topes (INV-030): 10 por minuto por número; `WHATSAPP_MENSAJES_POR_DIA` (50) por usuario y
   `WHATSAPP_MENSAJES_TOTALES_DIA` (300) en total al día; al pasarse se avisa una vez y se ignora el resto.
6. «ayuda» → ejemplos sin IA. Sin `ANTHROPIC_API_KEY` → aviso, nada se registra.
7. Una llamada a Claude con las herramientas `registrar_movimientos`, `deshacer_ultimo`, `corregir_ultimo`.
   El backend valida y ejecuta, y responde con el resultado. Si Claude falla → aviso «No se registró nada».

## Enlace desde la app (con sesión; errores comunes 401/503 en CT-002)
| Endpoint | Respuesta | Errores |
|---|---|---|
| `GET /whatsapp/enlace` | `{ "configurado": bool, "enlazado": bool, "telefono": "•••• 2233" \| null }` | — |
| `POST /whatsapp/enlace` | `{ "codigo": "FZ-123456", "vence_en_minutos": 10 }` (un solo uso; reemplaza el anterior del usuario) | 503 si WhatsApp no está configurado en el servidor |
| `DELETE /whatsapp/enlace` | `{ "message": "WhatsApp desconectado" }` | — |

## Validación de lo que propone la IA (igual que CT-003)
monto > 0 y ≤ 1e12 (2 decimales) · tipo `ingreso`/`gasto` · fecha `YYYY-MM-DD` entre hoy−366 días y mañana (si no,
hoy) · categoría: solo una propia del mismo tipo, por nombre sin tildes ni mayúsculas (si no, sin categoría) ·
medio de pago de la lista de INV-022 (si no, sin especificar) · descripción ≤ 255 · máximo 10 movimientos por
mensaje; si uno es inválido no se guarda ninguno. Deshacer/corregir: solo el último mensaje que registró algo por
WhatsApp, de las últimas 24 h, y solo transacciones del mismo usuario.
