# CHG-017 — Monitor de consumos (solo dueño)

- **Estado:** spec-aprobada (1-5 por el dueño; 6-15 decisiones provisionales del coordinador; 16-20 provisionales, tras la 2.ª validación; pendiente de re-validación)
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
- Actor y permisos: dueño = quien inicia sesión con el correo de `OWNER_EMAIL`, validado en el servidor en cada petición; a cualquier otro, o ante cualquier fallo al autorizar, 404 fail-closed (preguntas 11 y 12). Vocabulario: «Dueño» es el actor; no confundir con el «propietario del registro» de INV-001.
- Puntos de contador: `utils/asistente.py::llamar_claude` (cubre asistente y WhatsApp), `utils/email.py::send_verification_email` (solo envíos exitosos), `utils/whatsapp.py::enviar` y el webhook.
- Riesgos de seguridad (10): autorización por petición, 404 sin revelar al dueño, tokens nunca en respuestas/logs/errores de httpx, privilegios excesivos (los tokens actuales de WhatsApp/Brevo/Supabase escriben: usar tokens aparte), SSRF (URLs fijas en código, ids solo de config), solo agregados (sin correos ni teléfonos), `Cache-Control: no-store` solo en las respuestas al Dueño confirmado (200, 405, 429, 503; el 404 no lo lleva, pregunta 15) y caché corta, contadores en Supabase con RLS (INV-013/021), cuenta del dueño eliminada o correo re-registrado.

## 4. Preguntas abiertas
| # | Pregunta | Impacto | Respuesta | Quién |
|---|---|---|---|---|
| 1 | ¿Se aprueba el actor «Dueño» y acotar INV-012 (el monitor no es un endpoint de diagnóstico)? | Regla de negocio/seguridad | Aprobado tal como se propuso (2026-11-24) | Julián Zúñiga |
| 2 | Tokens «de solo lectura»: no todas las plataformas los ofrecen (Anthropic pide clave de administración y cuenta de organización). ¿Se acepta tokens separados con el menor permiso disponible y marcar «no disponible» lo que no se pueda leer? | Alcance y seguridad | Aprobado tal como se propuso (2026-11-24) | Julián Zúñiga |
| 3 | Contadores: ¿desde la puesta en marcha (sin histórico) y retención 90 días? | Datos | Aprobado tal como se propuso (2026-11-24) | Julián Zúñiga |
| 4 | ¿Basta la sesión normal del dueño o se pide reautenticar al entrar al panel? | Seguridad | Aprobado tal como se propuso (2026-11-24) | Julián Zúñiga |
| 5 | Si se elimina la cuenta del dueño o otra persona registra ese correo: el acceso se concede por correo verificado; ¿se acepta? | Seguridad | Aprobado tal como se propuso (2026-11-24) | Julián Zúñiga |
| 6 | (T0) INV-035 pide «caché corta» y «límite de frecuencia» sin cifras. ¿Qué valores? | Seguridad/cuotas | **Decidido por coordinador por defecto seguro, el dueño puede cambiarlo:** caché de 60 s por plataforma, 20 peticiones/min por dueño y timeout de 5 s por plataforma (valores fijos en CT-010 y NFR; son configuración, no contrato con el cliente) | coordinador (dueño puede cambiarlo) |
| 7 | (T0) La forma exacta de `datos` por plataforma y los ids de configuración dependen de lo que permita cada API con el token de menor permiso. | Alcance | **Decidido por coordinador por defecto seguro, el dueño puede cambiarlo:** CT-010 fija un esquema mínimo por plataforma (solo números, fechas ISO y cadenas de lista blanca) y una regla comprobable (INV-032). Los nombres exactos de los campos se confirman contra cada API al implementar; lo que no se pueda leer queda `no_disponible`; todo ajuste se registra en CT-010 **antes del cierre** del cambio. Si una plataforma exige plan de pago o escritura, queda «no disponible» y se avisa (REQ-N-006). | coordinador (dueño puede cambiarlo) |
| 8 | (T0) Ventana de los contadores en la respuesta. | Interfaz | **Decidido por coordinador por defecto seguro, el dueño puede cambiarlo:** la respuesta trae los últimos 30 días UTC; se retienen 90 días en la BD (INV-036). Sin parámetros | coordinador (dueño puede cambiarlo) |
| 9 | (T0) «Mensajes de WhatsApp recibidos»: ¿cuentan los de números desconocidos? | Datos | **Decidido por coordinador por defecto seguro, el dueño puede cambiarlo:** «recibidos» = solo mensajes de números enlazados que pasan la firma de Meta; los de números desconocidos y los de firma inválida **no** se cuentan (así un tercero no puede inflar el contador) | coordinador (dueño puede cambiarlo) |
| 10 | (T0) Purga de 90 días: ¿al escribir o con tarea aparte? | Diseño | **Decidido por coordinador por defecto seguro, el dueño puede cambiarlo:** purga oportunista al escribir un contador, como mucho una vez al día, sin tarea programada ni infraestructura nueva | coordinador (dueño puede cambiarlo) |
| 11 | (Validador, BLOQUEANTE-1) Qué responde la ruta cuando falla algo al autorizar (BD caída al verificar la sesión, sesión inválida, correo distinto, `OWNER_EMAIL` vacío). | Seguridad | **Decidido por coordinador por defecto seguro, el dueño puede cambiarlo:** ante **cualquier** fallo al autorizar, 404 fail-closed (indistinguible). 503 solo si ya se confirmó que es el dueño y falla la lectura de contadores. El 429 también se aplica solo tras confirmar al dueño | coordinador (dueño puede cambiarlo) |
| 12 | (Validador, BLOQUEANTE-2) Qué responde `/monitor/*` a un método distinto de GET. | Seguridad | **Decidido por coordinador por defecto seguro, el dueño puede cambiarlo:** no-dueño con **cualquier** método → 404 idéntico al de una ruta inexistente (cuerpo y cabeceras); el dueño con método distinto de GET → 405 | coordinador (dueño puede cambiarlo) |
| 13 | (Validador) CA-4 pedía tokens de «menor permiso disponible» como si fuera comprobable por código. | Seguridad/prueba | **Decidido por coordinador por defecto seguro, el dueño puede cambiarlo:** token creado con el menor permiso que la plataforma ofrezca; si no permite solo lectura, se documenta en ADR-008 y se verifica por **revisión de configuración**, no por prueba automatizada (deja de ser una invariante comprobable por código) | coordinador (dueño puede cambiarlo) |
| 14 | (Validador, menor) Mitigación opcional del riesgo aceptado en la pregunta 5 (correo del dueño re-registrado por otra persona). | Seguridad | **No se implementa; deuda anotada** en ADR-008 (p. ej. fijar además el id de usuario del dueño en configuración). Si el dueño lo quiere, requiere cambio de spec | coordinador (deuda) |
| 15 | (T0, residual) Las respuestas 404 bajo `/monitor/*` llevan `Cache-Control: no-store` (INV-035); un 404 fuera de ese prefijo no. Un observador podría inferir que el prefijo `/monitor` existe, no que el usuario sea o no el dueño. ¿Se acepta, o se aplica `no-store` a todos los 404 de la API? | Seguridad | **Decidido por coordinador por defecto seguro, el dueño puede cambiarlo:** el 404 del no-Dueño es byte a byte idéntico al 404 normal de una ruta inexistente de la API, **sin** `Cache-Control: no-store` añadido (un 404 no se cachea de forma útil y así no delata el prefijo). `no-store` aplica solo al 200 del Dueño, a su 429 y a su 503 (y 405). Las pruebas comparan contra `/api/v1/no-existe` y `/api/v1/monitor/no-existe` | coordinador (dueño puede cambiarlo) |
| 16 | (2.ª validación, BLOQUEANTE) OPTIONS y HEAD sobre `/monitor/*`. | Seguridad | **Provisional del coordinador, el dueño puede cambiarlo:** el preflight CORS (OPTIONS) queda fuera de INV-033 y lo atiende el middleware CORS como en toda la API (responde igual en cualquier ruta, no revela nada; no se promete 404 idéntico). HEAD cuenta como método no GET: no-Dueño 404, Dueño 405. La prueba del POST se parametriza con HEAD | coordinador (dueño puede cambiarlo) |
| 17 | (2.ª validación, IMP-3) Cómo decide la interfaz mostrar el enlace «Monitor». | Interfaz/seguridad | **Provisional:** campo booleano `es_dueno` en `GET /users/me` (CT-002): solo informa a cada usuario sobre sí mismo, nunca el correo del dueño; `false` por defecto, con `OWNER_EMAIL` vacío o si falla la comprobación. `/dashboard/monitor` muestra «no encontrada» si el backend da 404 | coordinador (dueño puede cambiarlo) |
| 18 | (2.ª validación, IMP-4/5) Límite numérico de tiempo. | Rendimiento | **Provisional:** resumen en < 6 s en el peor caso; contadores y plataformas en paralelo; plazo TOTAL de 5 s por plataforma con `asyncio.wait_for` (no solo timeout por fase de `httpx`); los fallos (`no_disponible`) se cachean 15 s. Prueba: `test_inv034_resumen_responde_en_menos_de_6s_en_el_peor_caso` | coordinador (dueño puede cambiarlo) |
| 19 | (2.ª validación, IMP-6) Subrutas inexistentes bajo `/monitor/*`. | Seguridad | **Provisional:** para cualquier usuario (Dueño incluido) y método, 404 normal; la comparación se pide sin sesión y con sesión de no-Dueño. Un no-Dueño sobre el límite recibe 404, nunca 429 | coordinador (dueño puede cambiarlo) |
| 20 | (2.ª validación, menores 1-4) Criterios conservadores: `datos` solo `int`/`float` no negativos (nunca `bool`); fechas-instante UTC ISO-8601 con «Z»; Anthropic o `no_disponible` o solo campos de su lista; `claude.asistente`/`claude.whatsapp` siempre presentes con ceros; nombres de métrica fijos (CT-010, `02-ENTITIES.md`); purga de filas con fecha < hoy − 90 días y marca de «última purga» en la propia tabla (fila `purga`/`general`) para varias instancias; atomicidad probada solo en `06_comprobar_monitor.sql`; el 405 del Dueño cuenta para el límite 20/min; el camino 404 sin límite propio es riesgo aceptado (ADR-008) | Datos/seguridad | **Provisional del coordinador, el dueño puede cambiarlo** | coordinador (dueño puede cambiarlo) |

## 5. Spec afectada
REQUIREMENTS (§3, REQ-F-018, REQ-N-003, §8), 05-INVARIANTS (INV-012 acotado, INV-031..036), CT-010, ADR-008, UC-014, BDD-MONITOR, TRACEABILITY, BL-035 (T0, 2026-11-24) · **Aprobación de la spec:** Julián Zúñiga, 2026-11-24 («Si apruebo todo del 1 al 5 implementa todo»). Alcance aprobado = lo descrito en §3 y las propuestas de §4.

## 6. Plan de tareas
| Tarea | Alcance | Depende de | Estado | Ciclos |
|---|---|---|---|---|
| T1 | Migración SQL `contadores_diarios` (RLS, clave única) + `backend/sql/pruebas/06_comprobar_monitor.sql` + modelo/utilidad de contadores (nunca rompe el flujo) + ganchos en `llamar_claude`, `send_verification_email`, `enviar` y webhook | spec | pendiente | 0 |
| T2 | Config (`OWNER_EMAIL`, `MONITOR_*`), clientes de plataformas (Railway, Anthropic, Meta, Supabase, Vercel, Brevo), ruta `GET /monitor/resumen`, `es_dueno` en `/users/me`, `tests/test_monitor.py` | T1 | pendiente | 0 |
| T3 | Frontend: página `/dashboard/monitor`, enlace condicional por `es_dueno`, proxy, pruebas | T2 | pendiente | 0 |
| T4 | Validación completa, revisión independiente, trazabilidad, docs de despliegue | T1-T3 | pendiente | 0 |

## 7. Registro de ejecución
| Fecha | Agente | Acción | Resultado / evidencia |
|---|---|---|---|
| 2026-11-24 | coordinador | Pedido registrado | Archivo creado |
| 2026-11-24 | clasificador | Clasificación | alto / completo / 88 %; detenido a la espera de aprobación de la spec |
| 2026-11-24 | generador | Corrección de la spec tras el informe del validador (BLOQUEANTE-1/2, IMPORTANTE, MENORES 1-7) | Sin código. Decisiones de §4 (6 a 15) aplicadas en REQUIREMENTS, glosario, entidades, estados, INV-031..036, CT-010, UC-014, BDD-MONITOR, ADR-008, NFR y TRACEABILITY; pendiente de re-validación |
| 2026-11-24 | generador | Corrección de la spec tras la 2.ª validación (bloqueante OPTIONS/HEAD, IMP-1 a IMP-6, menores 1-5) | Sin código. Decisiones 16 a 20 de §4 (provisionales) aplicadas en CT-010, CT-002 (`es_dueno`), UC-014, REQUIREMENTS, INV-031..036, 02-ENTITIES, BDD-MONITOR, ADR-008, NFR y TRACEABILITY; lista de pruebas unificada en INV, BDD y TRACEABILITY; pendiente de re-validación |

## 8. Cierre
- **Aprobación humana final:** pendiente
