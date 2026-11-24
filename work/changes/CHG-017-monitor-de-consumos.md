# CHG-017 — Monitor de consumos (solo dueño)

- **Estado:** spec-pendiente
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
| 1 | ¿Se aprueba el actor «Dueño» y acotar INV-012 (el monitor no es un endpoint de diagnóstico)? | Regla de negocio/seguridad | pendiente | dueño |
| 2 | Tokens «de solo lectura»: no todas las plataformas los ofrecen (Anthropic pide clave de administración y cuenta de organización). ¿Se acepta tokens separados con el menor permiso disponible y marcar «no disponible» lo que no se pueda leer? | Alcance y seguridad | pendiente | dueño |
| 3 | Contadores: ¿desde la puesta en marcha (sin histórico) y retención 90 días? | Datos | pendiente | dueño |
| 4 | ¿Basta la sesión normal del dueño o se pide reautenticar al entrar al panel? | Seguridad | pendiente | dueño |
| 5 | Si se elimina la cuenta del dueño o otra persona registra ese correo: el acceso se concede por correo verificado; ¿se acepta? | Seguridad | pendiente | dueño |

## 5. Spec afectada
_(pendiente)_ · **Aprobación de la spec:** pendiente

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
