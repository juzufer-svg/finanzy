# ADR-003 — Librerías de autenticación y límites de frecuencia

- **Estado:** aceptada
- **Fecha:** 2026-11-22 · **Decide:** dueño del proyecto

## Contexto
`python-jose` 3.3.0 y `python-multipart` 0.0.6 tenían vulnerabilidades publicadas; `passlib` no se mantiene.
Los endpoints de correo podían usarse para agotar el cupo de Brevo o enviar correos a terceros.

## Decisión
- JWT con **PyJWT**, solo algoritmos HMAC, `exp` y `sub` obligatorios (INV-011). Los tokens emitidos antes siguen siendo válidos.
- Contraseñas con **bcrypt** directo; se recortan a 72 bytes para mantener compatibilidad con los hashes de passlib (INV-015).
- Limitadores en memoria con ventana deslizante (`core/rate_limit.py`) e IP del cliente tomada del primer valor de
  `X-Forwarded-For` (Vercel lo reemplaza con la IP real) (INV-010).
- Dependencias fijadas en `requirements.txt` y auditadas con `pip-audit` (REQ-N-004).

## Consecuencias
- Positivas: 0 vulnerabilidades conocidas; abuso de correo acotado.
- Deuda aceptada: límites en memoria (se reinician con cada despliegue); quien llame directo a la URL de Railway
  puede falsear la IP, pero los límites por correo y el tope global siguen aplicando.
- Pendiente: invalidar sesiones al cambiar la contraseña (pregunta abierta 4).
