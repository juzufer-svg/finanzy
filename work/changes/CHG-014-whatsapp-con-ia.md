# CHG-014 — Registrar ingresos y gastos por WhatsApp con IA

- **Estado:** aprobado por el dueño (2026-11-23: «Sí apruebo la 1 y la 2»: la ampliación de INV-016 y el push a `main`). Falta el SQL y la configuración en Meta/Railway. La cuenta de WhatsApp Business en Meta está restringida (error 131031) y el dueño pidió revisión a Meta
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
reintentos de webhooks (posibles duplicados), versión `v25.0` de la Graph API.

## 4. Spec
REQ-F-017, INV-029, INV-030, CT-009, UC-013, ADR-007, BDD-WHATSAPP, TRACEABILITY, `docs/WHATSAPP.md`.

## 5. Evidencia
- Backend: 278 pruebas (46 nuevas en `tests/test_whatsapp.py`, con Claude y Meta simulados), pyflakes 0.
- SQL: `probar.sh` («OK: tablas de WhatsApp con RLS…») y ejecución sentencia por sentencia (como el SQL Editor).
- Frontend: eslint 0, `npm test` 28/28, build correcto. Playwright: Perfil → Conectar → webhook firmado con el
  código → «Conectado •••• 2233».
- Pendiente de prueba real: depende de la configuración del dueño en Meta y Railway (no hay acceso desde aquí).

## 6. Revisión independiente
**Ciclo 1: BLOQUEADO** (confianza 85 %). Correcciones:
| # | Severidad | Hallazgo | Respuesta |
|---|---|---|---|
| H1 | Importante | «corregir» con campos vacíos borraba categoría, medio, nota y movía la fecha | Esquema propio para corregir («omite lo que no cambia») y los vacíos se ignoran. `test_h1_*` |
| H2 | Importante (seguridad) | El enlace sobrevivía a un cambio o restablecimiento de contraseña | Cambiar o restablecer la contraseña desconecta WhatsApp (INV-016 ampliado). `test_h2_*`. **Decisión de seguridad pendiente del visto bueno del dueño** |
| H3 | Importante | Fallo a mitad del lote dejaba datos a medias y sin aviso | Lote todo o nada (se revierte lo creado) y aviso al número enlazado ante errores. `test_h3_*` |
| H4 | Menor | Un código podía reemplazar el vigente de otra persona | Se sortea de nuevo si ya existe. `test_h4_*` |
| H5 | Menor | «ayuda» gastaba cupo y exigía la clave de IA | Se atiende antes de topes y clave. `test_h5_*` |
| H6 | Menor | El aviso del tope global decía el del usuario | Textos distintos y «en las próximas horas». `test_h6_*` |
| H7 | Menor | Monto como texto «85.000» se guardaba como 85 | Solo números. `test_h7_*` |
| H8 | Menor | Fallo al enlazar sin aviso | Se avisa con el mensaje de error general (H3). Un solo worker: sin carrera práctica |
| H9 | Menor | Números desconocidos dejaban filas sin limpieza | No se guarda nada de números desconocidos; limpieza de ids de más de 7 días cada 10 min. `test_h9_*` |
| H10 | Menor | Payloads con tipos raros daban 500; no se comprobaba el número | Lectura robusta y se ignoran mensajes de otro `phone_number_id`. `test_h10_*` |
| H11 | Menor | «Ya lo envié» sin señal; esqueleto sin `aria-busy` | Aviso si aún no llega; `role="status"` y `aria-busy` |
| H12 | Menor | Guía incompleta | Despliegue previo, memoria tras despliegues, destinatarios de prueba, variables opcionales |
| H13 | Menor | REQ-F-017 decía «Verificado» | «En revisión» hasta la prueba real |
Resultado: backend 296 pruebas.

**Ciclo 2: APROBADO CON OBSERVACIONES** (confianza 88 %; sin bloqueantes en el código; escala al dueño por la ampliación
de INV-016). Atendidas:
- Desconectar WhatsApp **antes** de cambiar o restablecer la contraseña; si falla, 503 y no cambia nada
  (`test_inv016_si_no_se_puede_desconectar_*`, `test_inv016_restablecer_tampoco_*`).
- Si falla también la reversión del lote, el aviso no afirma «no se registró nada» (`test_si_tambien_falla_la_reversion_*`).
- Tope por minuto también para «ayuda» y lo que no es texto (`test_inv030_ayuda_tambien_*`).
- La desconexión vive en `WhatsappDB` (sin import entre rutas); la reversión limpia también los registros en memoria.
- Documentos: CT-001/002, UC-003, UC-013, CT-009, BDD-WHATSAPP y CONTEXTO.
Resultado: backend 300 pruebas. Ciclos usados: 2 de 3. **Pendiente: visto bueno del dueño a la regla de INV-016 y al push.**

## 7. Aprobación y despliegue
- 2026-11-23: el dueño aprueba que cambiar o restablecer la contraseña desconecte WhatsApp (INV-016) y el push a `main`.
- Versión de la Graph API por defecto: `v25.0` (la que muestra el panel de Meta del dueño).
- Prueba en Meta: los mensajes entrantes llegan al webhook de prueba; el envío falla con 131031 «Business Account locked» (restricción de la cuenta en Meta, no del código).
- 2026-11-23: página pública de privacidad `frontend/app/privacidad/page.tsx` (`/privacidad`, enlazada desde la portada). Meta la exige para publicar la app; su sección 6 sirve como instrucciones de eliminación de datos. Aprobada por el dueño («Si créala… y despliega en main»).
- 2026-11-23: página pública de condiciones del servicio `frontend/app/terminos/page.tsx` (`/terminos`) y diseño común `components/LegalPage.tsx` para ambas páginas legales. Pedida por el dueño para la configuración de Meta.
