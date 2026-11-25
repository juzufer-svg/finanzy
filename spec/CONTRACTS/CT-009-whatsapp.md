# CT-009 — WhatsApp `/api/v1/whatsapp`

- **Versión:** v1.1 (CHG-014; CHG-019 fase c: cuenta nombrada por el usuario) · **UC:** UC-013 · **REQ:** F-017 · **ADR:** ADR-007 · **INV:** INV-029, INV-030

## Webhook de Meta (sin sesión; lo llama Meta directamente al backend)
| Endpoint | Entrada | Respuesta |
|---|---|---|
| `GET /whatsapp/webhook` | `hub.mode=subscribe`, `hub.verify_token`, `hub.challenge` | 200 texto plano = `hub.challenge` si el token coincide con `WHATSAPP_VERIFY_TOKEN`; si no, 403 |
| `POST /whatsapp/webhook` | Cuerpo de Meta + cabecera `X-Hub-Signature-256: sha256=<HMAC-SHA256(cuerpo, WHATSAPP_APP_SECRET)>` | 403 «Firma inválida» si falta o no coincide (o no hay App Secret). Si es válida, 200 `{"ok": true}` de inmediato y los mensajes se procesan en segundo plano |

Diagnóstico (log de Railway, sin teléfono, texto ni ids): cuando Meta avisa que una respuesta **no se entregó** (`statuses` con `failed`)
se escribe `[whatsapp] Meta no entregó una respuesta: código N título`; y si un aviso trae mensajes de otro `phone_number_id`
se escribe `[whatsapp] Mensajes ignorados…` (una variable `WHATSAPP_PHONE_NUMBER_ID` mal puesta descartaba todo en silencio).

Procesamiento de cada mensaje de texto (en orden):
0. Mensajes dirigidos a otro número de la cuenta de Meta (`metadata.phone_number_id` distinto) se ignoran.
1. Un número no enlazado que no envía un código se ignora sin guardar nada. Si el id del mensaje ya se procesó → se ignora (Meta reintenta; los ids se guardan 7 días).
2. Si el texto es un código `FZ-NNNNNN` (5 intentos/hora por número) → si es válido y vigente, enlaza el número a la
   cuenta que lo generó y responde «✅ ¡Listo!»; si no, responde que no es válido.
3. Si el número no está enlazado → se ignora sin responder ni llamar a la IA.
4. Mensajes que no son texto → responde que solo entiende texto (sin IA).
5. Topes (INV-030): 10 por minuto por número; `WHATSAPP_MENSAJES_POR_DIA` (50) por usuario y
   `WHATSAPP_MENSAJES_TOTALES_DIA` (300) en total al día; al pasarse se avisa una vez y se ignora el resto.
6. «ayuda» → ejemplos sin IA y sin gastar cupo (antes de los topes). Sin `ANTHROPIC_API_KEY` → aviso, nada se registra. Topes: el aviso distingue el tope propio del global.
7. Una llamada a Claude con las herramientas `registrar_movimientos`, `deshacer_ultimo`, `corregir_ultimo`.
   El backend valida y ejecuta, y responde con el resultado. Si Claude falla → aviso «No se registró nada».
   Registrar es todo o nada: si falla a mitad del lote se borra lo creado y se avisa. `corregir_ultimo` solo cambia
   los campos que trae con valor (un campo vacío no borra nada). Un error inesperado se avisa al número enlazado (o a quien envió un código de enlace, como máximo 5 por hora). Si además falla la reversión, el aviso dice que puede haber quedado algo registrado.
8. Cambiar o restablecer la contraseña desconecta el número **antes** de cambiarla; si no se puede, 503 y nada cambia (INV-016).

El tope por minuto aplica también a «ayuda» y a los mensajes que no son texto (sin gastar el cupo diario).

## Enlace desde la app (con sesión; errores comunes 401/503 en CT-002)
| Endpoint | Respuesta | Errores |
|---|---|---|
| `GET /whatsapp/enlace` | `{ "configurado": bool, "enlazado": bool, "telefono": "•••• 2233" \| null }` | — |
| `POST /whatsapp/enlace` | `{ "codigo": "FZ-123456", "vence_en_minutos": 10 }` (un solo uso; reemplaza el anterior del usuario) | 503 si WhatsApp no está configurado en el servidor |
| `DELETE /whatsapp/enlace` | `{ "message": "WhatsApp desconectado" }` | — |

## Validación de lo que propone la IA (igual que CT-003)
monto > 0 y ≤ 9 999 999 999,99 (se redondea a 2 decimales) · tipo `ingreso`/`gasto` · fecha `YYYY-MM-DD` entre hoy−366 días y mañana (si no,
hoy) · categoría: solo una propia del mismo tipo, por nombre sin tildes ni mayúsculas (si no, sin categoría) ·
medio de pago de la lista de INV-022 (si no, sin especificar) · descripción ≤ 255 · máximo 10 movimientos por
mensaje; si uno es inválido no se guarda ninguno. Deshacer/corregir: solo el último mensaje que registró algo por
WhatsApp, de las últimas 24 h, y solo transacciones del mismo usuario.

## Cuentas de dinero en WhatsApp (CHG-019, fase c)
La herramienta de la IA que crea transacciones admite un campo opcional `cuenta` (**nombre de una cuenta de dinero**) que la IA solo debe rellenar si la persona
nombró la cuenta de dinero. El backend la busca entre las **cuentas de dinero no archivadas del usuario del número enlazado** (sin distinguir mayúsculas ni tildes)
y valida saldo y archivada con las mismas reglas de la app (INV-029, INV-048); si no se nombra, la transacción queda **sin cuenta**; si
se nombra y no existe, está archivada o no alcanza el saldo, **no se registra nada** y la respuesta lo explica. A Claude se le envían
solo los nombres de las cuentas de dinero no archivadas (sin ids ni saldos). WhatsApp **no** crea transferencias.

## «Deshacer» y «corregir» con cuenta de dinero (CHG-019, fase a)
Si un movimiento del lote tiene cuenta de dinero (asignada desde la app) y la BD rechaza el cambio, la respuesta por WhatsApp es un texto fijo y no se cambia nada: «No pude deshacerlo/corregirlo: dejaría la cuenta de dinero con saldo negativo…» (FZ001), «…la cuenta de dinero está archivada…» (FZ002) o «…el monto no cumple lo permitido…» (23514). Un lote con más de un movimiento en cuenta responde «No pude deshacerlo: varios de esos movimientos tienen cuenta de dinero…» y no borra nada. El webhook sigue respondiendo 200 y el mensaje queda marcado como procesado (INV-029).
