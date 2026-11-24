# CHG-017 — Monitor de consumos (solo dueño)

- **Estado:** spec-aprobada
- **Fecha:** 2026-11-24 · **Solicitante:** Julián Zúñiga (dueño)
- **Riesgo:** alto

## 1. Pedido original (literal, sin reinterpretar)
> Panel "Monitor" solo para el dueño (Julián Zúñiga): centraliza consumos de Railway, Claude, Meta/WhatsApp, Supabase, Vercel y Brevo. Contadores propios (tokens de Claude, mensajes WhatsApp, correos) + lectura de las APIs de cada plataforma con tokens de solo lectura en variables de entorno. Acceso restringido al dueño por variable OWNER_EMAIL (sin hardcodear). Modo completo (seguridad).

Contexto: el dueño respondió «Conectemos todas las plataformas y el monitor lo dejas solo para mí Julián Zúñiga».

## 2. Clasificación
Tipo: nueva-funcionalidad (+ cambio de regla de acceso). Riesgo: **alto**. Modo: **completo**. Confianza 88 % (clasificación); baja en el diseño por tokens.
Requiere cambio de spec: nuevo actor «Dueño» (REQUIREMENTS §3 dice que no hay administradores), posible ampliación de INV-012/REQ-N-003 («sin endpoints de diagnóstico»), nuevo REQ-F-018, CT-010, ADR-008, INV, UC y BDD.

## 3. Análisis
- Alcance: página «Monitor» solo lectura (GET); contadores propios en Supabase (tokens de Claude, mensajes WhatsApp enviados/recibidos, correos Brevo) y lectura de Railway, Anthropic, Meta, Supabase, Vercel y Brevo. Fuera de alcance: cualquier acción de escritura (reiniciar, cambiar variables, borrar).
- Actor y permisos: dueño = quien inicia sesión con el correo de `OWNER_EMAIL`, validado en el servidor en cada petición (fail-closed si falta); a cualquier otro, 404.
- Puntos de contador: `utils/asistente.py::llamar_claude` (cubre asistente y WhatsApp), `utils/email.py::send_verification_email` (solo envíos exitosos), `utils/whatsapp.py::enviar` y el webhook.
- Riesgos de seguridad (10): autorización por petición, 404 sin revelar al dueño, tokens nunca en respuestas/logs/errores de httpx, privilegios excesivos (los tokens actuales de WhatsApp/Brevo/Supabase escriben: usar tokens aparte), SSRF (URLs fijas en código, ids solo de config), solo agregados (sin correos ni teléfonos), `Cache-Control: no-store` y caché corta, contadores en Supabase con RLS (INV-013/021), cuenta del dueño eliminada o correo re-registrado.

## 4. Preguntas abiertas
| # | Pregunta | Impacto | Respuesta | Quién |
|---|---|---|---|---|
| 1 | ¿Se aprueba el actor «Dueño» y acotar INV-012 (el monitor no es un endpoint de diagnóstico)? | Regla de negocio/seguridad | Aprobado tal como se propuso (2026-11-24) | Julián Zúñiga |
| 2 | Tokens «de solo lectura»: no todas las plataformas los ofrecen (Anthropic pide clave de administración y cuenta de organización). ¿Se acepta tokens separados con el menor permiso disponible y marcar «no disponible» lo que no se pueda leer? | Alcance y seguridad | Aprobado tal como se propuso (2026-11-24) | Julián Zúñiga |
| 3 | Contadores: ¿desde la puesta en marcha (sin histórico) y retención 90 días? | Datos | Aprobado tal como se propuso (2026-11-24) | Julián Zúñiga |
| 4 | ¿Basta la sesión normal del dueño o se pide reautenticar al entrar al panel? | Seguridad | Aprobado tal como se propuso (2026-11-24) | Julián Zúñiga |
| 5 | Si se elimina la cuenta del dueño o otra persona registra ese correo: el acceso se concede por correo verificado; ¿se acepta? | Seguridad | Aprobado tal como se propuso (2026-11-24) | Julián Zúñiga |
| 6 | (T0) INV-035 pide «caché corta» y «límite de frecuencia» sin cifras. CT-010 propone por defecto caché de 60 s por plataforma y 20 peticiones/min por dueño, como configuración. ¿Se confirman? | Seguridad/cuotas | Abierta (propuesta en CT-010) | Julián Zúñiga |
| 7 | (T0) La forma exacta de `datos` por plataforma y los ids de configuración (proyecto, servicio, organización) dependen de lo que permita cada API con el token de menor permiso; no se puede fijar sin probarlas. ¿Se define en la implementación (T1+) y se informa antes de cerrar? Si una plataforma exige plan de pago o permisos de escritura, queda «no disponible» y se avisa (REQ-N-006). | Alcance | Abierta | Julián Zúñiga / coordinador |
| 8 | (T0) Ventana de los contadores en la respuesta: CT-010 devuelve todos los días retenidos (hasta 90) sin parámetros. ¿Basta, o se quiere un rango fijo más corto en pantalla? | Interfaz | Abierta | Julián Zúñiga |
| 9 | (T0) «Mensajes de WhatsApp recibidos»: ¿cuentan solo los de números enlazados procesados, o también los ignorados (número desconocido)? CT-010 deja «mensajes procesados de Meta» sin contar los descartados por firma inválida. | Datos | Abierta | Julián Zúñiga |
| 10 | (T0) Purga de 90 días: ¿al escribir un contador (sin tarea programada) o con una tarea aparte? No se fija en la spec; propuesta: purga oportunista al escribir, sin infraestructura nueva. | Diseño | Abierta | coordinador |

## 5. Spec afectada
REQUIREMENTS (§3, REQ-F-018, REQ-N-003, §8), 05-INVARIANTS (INV-012 acotado, INV-031..036), CT-010, ADR-008, UC-014, BDD-MONITOR, TRACEABILITY, BL-035 (T0, 2026-11-24) · **Aprobación de la spec:** Julián Zúñiga, 2026-11-24 («Si apruebo todo del 1 al 5 implementa todo»). Alcance aprobado = lo descrito en §3 y las propuestas de §4.

## 6. Plan de tareas
| Tarea | Alcance | Depende de | Estado | Ciclos |
|---|---|---|---|---|

## 7. Registro de ejecución
| Fecha | Agente | Acción | Resultado / evidencia |
|---|---|---|---|
| 2026-11-24 | coordinador | Pedido registrado | Archivo creado |
| 2026-11-24 | clasificador | Clasificación | alto / completo / 88 %; detenido a la espera de aprobación de la spec |

## 8. Cierre
- **Aprobación humana final:** pendiente
