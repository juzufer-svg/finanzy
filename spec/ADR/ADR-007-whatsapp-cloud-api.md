# ADR-007 — Registro por WhatsApp con la Cloud API de Meta y un agente de IA con escritura limitada

- **Estado:** aprobado por el dueño (2026-11-23)
- **Fecha:** 2026-11-23 · **Decide:** dueño del proyecto

## Contexto
El dueño quiere registrar ingresos y gastos desde WhatsApp en lenguaje libre, sin abrir la app y sin costo
(REQ-F-017). Su número personal no puede conectarse a la API (quedaría fuera de la app de WhatsApp).

## Alternativas evaluadas
| Opción | Pros | Contras |
|---|---|---|
| **WhatsApp Cloud API oficial + número de prueba de Meta** | Oficial, mensajes entrantes gratis, 1.000 respuestas gratis/mes por número; sin tarjeta Meta nunca cobra | Configuración inicial en Meta; el número de prueba es de desarrollo |
| Librerías no oficiales (Baileys, whatsapp-web.js) | Usan el número personal | Violan las condiciones de WhatsApp (riesgo de bloqueo), proceso extra 24/7 |
| Twilio u otros intermediarios | Fácil | De pago |
| Bot de Telegram | 100 % gratis | El dueño prefiere WhatsApp |

Interpretación: formato fijo (gratis) vs. **IA en lenguaje libre** (elegida por el dueño; ~0,0003 US$/mensaje).

## Decisión
- Cloud API oficial con el número de prueba. Webhook directo al backend (Railway), no por el proxy de Vercel
  (exige CSRF y no reenvía la firma). Firma `X-Hub-Signature-256` verificada en cada petición.
- Un **agente aparte** del Asistente: herramientas solo para crear transacciones y deshacer o corregir las que
  creó el propio WhatsApp. El Asistente de la app sigue siendo de solo lectura (INV-023 sin cambios).
- La IA solo propone; el backend valida con las reglas de la app. El usuario sale del número enlazado.
- Una llamada a Claude por mensaje; la respuesta de confirmación la arma el backend.
- Registro inmediato sin confirmación (con «deshacer»), montos en COP, tope de 50 mensajes por día.
- Cambiar o restablecer la contraseña desconecta WhatsApp (INV-016 ampliado, aprobado por el dueño el 2026-11-23).

## Consecuencias
- Nuevas variables en Railway (`WHATSAPP_*`) y migración `backend/sql/2026-11-23_whatsapp.sql`.
- Códigos de enlace, memoria corta de la conversación y topes viven en memoria: se reinician con cada despliegue
  (hay que generar otro código si estaba pendiente).
- Si Meta retira el número de prueba, se cambia `WHATSAPP_PHONE_NUMBER_ID` y se vuelve a enlazar.
