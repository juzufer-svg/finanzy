# ADR-008 — Monitor de consumos solo para el dueño, con contadores propios y lectura de plataformas

- **Estado:** aprobado por el dueño (2026-11-24, CHG-017, preguntas 1 a 5)
- **Fecha:** 2026-11-24 · **Decide:** dueño del proyecto

## Contexto
El dueño quiere ver en un solo lugar los consumos de Railway, Claude (Anthropic), Meta/WhatsApp, Supabase, Vercel y
Brevo para controlar costos y cuotas (REQ-F-018). Hasta ahora la spec decía que no hay roles de administrador y que no
hay endpoints de diagnóstico (REQ-N-003, INV-012).

## Alternativas evaluadas
| Opción | Pros | Contras |
|---|---|---|
| Entrar a la consola de cada plataforma | Sin código | Seis sitios, sin vista conjunta |
| Solo contadores propios | Sin tokens extra, mínima superficie | No muestra saldos, cuotas ni consumo real de Railway, Supabase o Vercel |
| **Contadores propios + lectura de las APIs con tokens propios del Monitor** (elegida) | Vista conjunta; cifras reales | Más secretos que proteger; no todas las plataformas ofrecen tokens de solo lectura |
| Rol de administrador general en la app | Flexible | Amplía privilegios más de lo pedido |

## Decisión
- Nuevo actor **Dueño** (distinto del «propietario del registro» de INV-001): quien inicia sesión con el correo de
  `OWNER_EMAIL` (variable de entorno, sin escribirlo en el código). Su único privilegio es ver el Monitor. Se valida en
  el servidor en cada petición con `hmac.compare_digest`; **fail-closed**: a los demás, y ante cualquier fallo al
  autorizar (BD caída, sesión inválida, `OWNER_EMAIL` vacío), 404; 503 y 429 solo tras confirmar al Dueño (INV-031).
  Un no-Dueño con cualquier método recibe el mismo 404; el Dueño con un método distinto de GET, 405 (INV-033).
  Estas reglas las fijó el coordinador por defecto seguro y el Dueño puede cambiarlas (CHG-017 §4, preguntas 11 y 12).
- INV-012 y REQ-N-003 se acotan: el Monitor no es un endpoint de diagnóstico y tampoco expone secretos (INV-032).
- Meta/WhatsApp: `conversation_analytics` ya no existe en la API de Meta (verificado con el token del dueño). Se usa
  `pricing_analytics.start().end().granularity(DAILY)` (sin `.dimensions`, que con forma errónea da 400) sobre la
  cuenta WABA: se muestran los **mensajes facturables del mes**; un 200 sin `pricing_analytics` equivale a 0.
- Solo lectura (GET). Sin acciones sobre las plataformas (INV-033).
- Contadores propios en Supabase, agregados por día, sin datos personales, desde la activación y con retención de
  90 días (purga oportunista al escribir, como mucho una vez al día, sin tarea programada); la respuesta muestra los
  últimos 30 días; «recibidos» de WhatsApp cuenta solo números enlazados; su escritura nunca rompe el flujo
  principal (INV-036).
- Lectura de las seis plataformas con tokens **propios** `MONITOR_*`, distintos de los de envío o escritura y con
  el menor permiso que la plataforma ofrezca. Algunas plataformas no ofrecen tokens de solo lectura (p. ej. Anthropic
  pide clave de administración y cuenta de organización): se acepta el menor permiso disponible y lo que no se pueda
  leer se muestra «no disponible» (aprobado, pregunta 2). Que cada token tenga ese menor permiso y sea distinto de los
  de escritura **se verifica por revisión de configuración, no por prueba automatizada**. Registro por plataforma
  (permiso elegido y si admite solo lectura): _se completa al crear los tokens, antes del cierre de CHG-017_.
  Estado conocido tras implementar (CHG-017 T2/T4):
  - **Supabase: función SQL de solo lectura (CHG-017).** El tamaño de la BD se lee con la RPC `public.tamano_bd()`
    (`backend/sql/2026-11-24_monitor_tamano_bd.sql`; EXECUTE solo para `service_role`) usando el cliente de Supabase
    que la app ya tiene: sin token nuevo y sin la Management API. Límite: 500 MB (plan gratuito), configurable con
    `MONITOR_SUPABASE_LIMITE_BD_BYTES`. Si el SQL no se ha ejecutado, la tarjeta queda «no disponible».
  - **Brevo: la clave es de acceso completo.** Brevo no ofrece claves de solo lectura; `MONITOR_BREVO_KEY` es una
    clave de API distinta de la de envío, pero con permisos completos. El código solo la usa en GET de cuenta e informe.
  - **Anthropic:** con clave de administración de una organización (`sk-ant-admin...`) se usa la fuente oficial y
    prevalece; otra clave no se envía. Sin ella (el Dueño no la tiene), la tarjeta estima el MES de Colombia (UTC−5) en curso con
    los contadores propios (INV-036), sumando los orígenes `asistente` y `whatsapp` (solo la API de Haiku de la app; la tarjeta aclara que no es el plan Pro ni incluye Claude Code), y el costo con una tabla fija
    de precios por modelo (`claude-haiku-5-5`: US$ 0,10/M entrada y US$ 0,50/M salida; precios del 2026-11-24, a
    revisar si cambia el modelo o el precio). Modelo desconocido: se omite el costo. Es una estimación y se rotula así.
  - **Verificación manual antes de producción:** los formatos de respuesta de las seis APIs se simularon en pruebas,
    pero **no se han probado con tokens reales**. Antes de desplegar, el Dueño comprueba una vez, con los tokens de
    producción, qué plataformas muestran datos y cuáles quedan «no disponible», y se registra aquí el resultado.
- `datos` de cada plataforma sigue un esquema mínimo de lista blanca (solo números, fechas ISO y cadenas fijas), CT-010 e INV-032.
- URLs de proveedores fijas en el código, ids solo de configuración, sin redirecciones, con timeout (INV-034); caché
  corta (60 s por plataforma, timeout de 5 s), límite de 20 peticiones por minuto por Dueño y `Cache-Control: no-store`
  solo en las respuestas al Dueño confirmado (200, 405, 429, 503; INV-035). El 404 del no-Dueño **no** lleva `no-store`:
  es byte a byte idéntico al 404 normal de una ruta inexistente de la API, para no delatar el prefijo `/monitor`
  (un 404 no se cachea de forma útil). Fijado por el coordinador por defecto seguro; el Dueño puede cambiarlo
  (CHG-017 §4, pregunta 15).
- La ruta se registra para cualquier método y `redirect_slashes` está desactivado (la barra final es un 404 normal).
  Solo el preflight CORS real (OPTIONS con `Origin` y `Access-Control-Request-Method`) queda fuera de INV-033: lo
  atiende el middleware CORS como en toda la API y responde igual en cualquier ruta; un OPTIONS sin esas cabeceras
  recibe el 404 (no-Dueño) o el 405 (Dueño). HEAD cuenta como método no GET (no-Dueño 404, Dueño 405). La interfaz muestra el enlace «Monitor» con
  el booleano `es_dueno` de `GET /users/me` (solo sobre el propio usuario; nunca el correo del dueño). Plazo total de
  5 s por plataforma con `asyncio.wait_for`, consultas en paralelo (resumen < 6 s), fallos en caché 15 s; purga con
  marca en la propia tabla (varias instancias); el 405 del Dueño cuenta para el límite. Provisional del coordinador;
  el Dueño puede cambiarlo (CHG-017 §4, preguntas 16 a 20).
- **Riesgo aceptado:** el camino 404 (no-Dueño, sin sesión) no tiene límite de frecuencia propio, para no crear
  diferencias observables con el 404 normal; el límite de 20/min solo protege al Dueño confirmado y las cuotas externas.
- Basta la sesión normal del dueño, sin reautenticar (aprobado, pregunta 4).
- El acceso se concede por correo verificado: si se elimina la cuenta del dueño y otra persona registra ese correo y
  lo verifica, obtendría el acceso. Riesgo aceptado por el dueño (pregunta 5).
- **Deuda anotada (no se implementa):** mitigación opcional de ese riesgo, p. ej. fijar además en la configuración el
  id de usuario del Dueño, o pedir reautenticación al entrar al Monitor. Requeriría cambio de spec (CHG-017 §4,
  pregunta 14). Otra mitigación opcional anotada: aviso en el log cuando el Dueño entre tras haberse eliminado su
  cuenta (BL-036).

## Consecuencias
- Nuevas variables en Railway: `OWNER_EMAIL`, `MONITOR_*` e ids de configuración (CT-010). Nueva migración en
  `backend/sql/` para la tabla de contadores (con RLS).
- Si falta un token, esa plataforma aparece «no disponible»; el resto sigue funcionando.
- Los tokens del Monitor son secretos adicionales: deben crearse con el mínimo permiso y rotarse si se filtran.
- Sin costo adicional (planes gratuitos, REQ-N-006); cualquier plataforma que exija plan de pago para su API se
  muestra «no disponible» y se avisa al dueño antes de pagar.

## Nota (CHG-017): gasto de Railway
Para mostrar el gasto en dólares del período (plan Hobby, US$5/mes) el cliente de Railway añade una segunda consulta
GraphQL de solo lectura (`query`, sin mutaciones) a la misma URL fija y con el mismo token de cuenta:
`project(id){ workspace{ customer{ currentUsage creditBalance billingPeriod{ start end } } } }`. Corre en paralelo con
`estimatedUsage` (`asyncio.gather` con `return_exceptions`) dentro del mismo plazo total de 5 s; si una falla, la otra
se muestra. Verificada contra la API real de Railway con una credencial de cuenta. `currentUsage` es un valor en caché
(puede ir algo retrasado). Sin costo adicional ni nuevas variables.

## Nota (CHG-017): días de los contadores en hora de Colombia
El dueño aprobó explícitamente que los **días de los contadores propios** corten a medianoche de Colombia (UTC−5 todo el año, sin horario de verano) y no de UTC. Es una excepción deliberada a «fechas en UTC» de `CLAUDE.md`. Se implementa con una zona fija (`timezone(timedelta(hours=-5))`, sin tzdata) en una única función `hoy_colombia()` (`backend/app/models/contadores.py`), que fija «hoy», el mes en curso del consumo estimado de Claude, la ventana de 30 días, `desde` y la purga a 90 días. Los instantes (`generado_en`, `actualizado_en`) siguen en UTC. Los periodos que define el proveedor (Railway, Meta, Brevo `enviados_hoy`) no cambian. El SQL no cambia: ninguna función usa `current_date`; recibe la fecha como parámetro (`p_fecha`, `p_hoy`). No se migran filas (aún no hay datos reales).

## Nota (CHG-017): plan, límite y uso por plataforma
Cada tarjeta muestra Plan, Límite, Uso actual y % del límite usado. Los límites son **constantes de referencia en el frontend** (`LIMITES_PLAN` en `frontend/lib/monitor.ts`, vigentes al 24 nov 2026 según la documentación de cada proveedor): no se consultan a las plataformas ni pasan por el backend, así que si un proveedor cambia sus planes hay que actualizarlas a mano. El uso sale de lo que ya devuelve `/monitor/resumen` (Railway: gasto del período; Supabase: tamaño de la BD; Brevo: enviados hoy; WhatsApp: suma de enviados del mes en curso de Colombia en los contadores propios). Vercel y Claude no tienen medida porcentual (sin barra). Sin cambios de API, SQL, tokens ni costo.
