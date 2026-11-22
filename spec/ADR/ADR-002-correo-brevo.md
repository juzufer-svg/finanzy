# ADR-002 — Correo transaccional con Brevo

- **Estado:** aceptada (reemplaza el uso de SendGrid)
- **Fecha:** 2026-11-22 · **Decide:** dueño del proyecto

## Contexto
Los códigos de verificación y de restablecimiento se envían por correo (REQ-F-001, REQ-F-003). La prueba gratuita de
SendGrid venció el 30/06/2026 y su plan más barato cuesta US$19.95/mes. Railway Hobby bloquea SMTP (25/465/587/2525).

## Alternativas evaluadas
| Opción | Pros | Contras |
|---|---|---|
| SendGrid Essentials | Sin cambios de código | US$19.95/mes |
| Gmail por SMTP | Gratis, buena entrega | Bloqueado en Railway Hobby |
| Railway Pro + SMTP | Permite SMTP | US$20/mes |
| **Brevo por API HTTPS** | Gratis (300/día), sin dominio propio (remitente verificado) | Correos desde @gmail.com pueden ir a spam al inicio |

## Decisión
Brevo, `POST https://api.brevo.com/v3/smtp/email` con cabecera `api-key`, HTML + texto plano.
Variables: `BREVO_API_KEY`, `FROM_EMAIL` (remitente verificado), `FROM_NAME`. Se eliminó todo el código de SendGrid.

## Consecuencias
- Tope propio de 250 correos/día (INV-010) para no agotar los 300 de Brevo.
- En producción sin clave: se registra el error y **no** se escribe el código en logs (INV-012).
- Si Brevo bloquea IPs desconocidas (401 "unrecognised IP"), desactivar el bloqueo de IP para claves API.
