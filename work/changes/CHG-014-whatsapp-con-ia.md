# CHG-014 — Registrar ingresos y gastos por WhatsApp con IA

- **Estado:** en revisión (falta revisión independiente, el visto bueno del dueño, el SQL y la configuración en Meta/Railway)
- **Fecha:** 2026-11-23 · **Riesgo:** medio-alto (escritura de datos por IA, integración externa) · modo `completo`

## 1. Pedido original
> la idea es usar WhatsApp con IA… si yo digo, hoy gasté tanto, hoy me ingresó tanto, pues que la IA… me ingrese
> eso… que no dependa de un mensaje específico, sino que sea libre.
> Sí, los montos van a ser en pesos colombianos… registrar directo… con la opción de deshacer, pero que no pida una
> confirmación… el tope diario… unos 50 mensajes por día. Implementa eso.

## 2. Decisiones del dueño
- Cloud API oficial de Meta con el **número de prueba** (su número personal no puede conectarse).
- **IA en lenguaje libre** (no formato fijo). Montos en **COP**. Registro **inmediato** sin confirmación, con
  «deshacer». Tope **50 mensajes/día**.
- Interpretación anotada: «si yo digo 80.000 se guarda como 85.000» se tomó como error de tipeo → se guarda lo dicho.

## 3. Verificado en la documentación oficial de Meta (no supuesto)
Precios (1.000 mensajes de servicio gratis al mes por número; sin método de pago no se cobra), pasos de creación de
la app, token permanente de usuario de sistema, verificación `hub.challenge` y firma `X-Hub-Signature-256`,
reintentos de webhooks (posibles duplicados), versión `v23.0` de la Graph API.

## 4. Spec
REQ-F-017, INV-029, INV-030, CT-009, UC-013, ADR-007, BDD-WHATSAPP, TRACEABILITY, `docs/WHATSAPP.md`.

## 5. Evidencia
- Backend: 278 pruebas (46 nuevas en `tests/test_whatsapp.py`, con Claude y Meta simulados), pyflakes 0.
- SQL: `probar.sh` («OK: tablas de WhatsApp con RLS…») y ejecución sentencia por sentencia (como el SQL Editor).
- Frontend: eslint 0, `npm test` 28/28, build correcto. Playwright: Perfil → Conectar → webhook firmado con el
  código → «Conectado •••• 2233».
- Pendiente de prueba real: depende de la configuración del dueño en Meta y Railway (no hay acceso desde aquí).
