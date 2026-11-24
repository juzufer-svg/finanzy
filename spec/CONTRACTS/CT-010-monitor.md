# CT-010 — Monitor del Dueño `/api/v1/monitor`

- **Versión:** v1 (CHG-017) · **UC:** UC-014 · **REQ:** F-018 · **ADR:** ADR-008 · **INV:** INV-031 a INV-036
- Solo lectura. Una única ruta. Errores comunes 401/503 de sesión (CT-002) **no** se usan aquí: ver «Errores».
- «Dueño» = actor definido en el glosario (no el «propietario del registro» de INV-001).

## Endpoint
| Endpoint | Entrada | Respuesta |
|---|---|---|
| `GET /monitor/resumen` | Sesión (cookie → `Authorization`, igual que el resto de la API). Sin parámetros | 200 con el objeto de abajo, solo si el correo de la sesión es el de `OWNER_EMAIL` (INV-031) |

No existen rutas de escritura ni de acciones. Regla por método sobre `/monitor/*` (INV-033):
- **No-Dueño** (sin sesión, sesión inválida o cualquier usuario) con **cualquier método** (GET, HEAD, POST, PUT, PATCH, DELETE, TRACE, PROPFIND, inventados, y OPTIONS sin cabeceras de preflight…) sobre la ruta existente (`/monitor/resumen`) → **404 idéntico** al de una ruta inexistente (mismo cuerpo y mismas cabeceras, byte a byte salvo `Date`). **HEAD cuenta como método distinto de GET.** La ruta se registra para **cualquier método** (no solo los habituales), así ningún método revela que existe. La barra final (`/monitor/resumen/`) no redirige: el backend desactiva `redirect_slashes`, de modo que es un 404 normal como cualquier ruta inexistente (ni el proxy del frontend ni las demás rutas dependen de redirecciones por barra final).
- **Dueño** con un método distinto de GET (incluido HEAD y cualquier método raro) sobre la ruta existente → **405** (`Allow: GET`), sin ejecutar nada, con `Cache-Control: no-store`.
- **Preflight CORS real** (OPTIONS con `Origin` y `Access-Control-Request-Method`): lo atiende el middleware CORS antes de llegar a la ruta, como en el resto de la API, y responde igual en cualquier ruta, así que no revela nada. Un OPTIONS **sin** esas cabeceras no es un preflight: llega a la ruta y recibe el 404 (no-Dueño) o el 405 (Dueño) de arriba.
- **Subrutas o rutas inexistentes** bajo `/monitor/*` (p. ej. `/monitor/no-existe`): **404 normal** de la API para cualquier usuario, incluido el Dueño, y con cualquier método (no 405). No se confirma al Dueño ni se aplica límite en ese camino. Prueba: la comparación del 404 se pide **sin sesión** y **con sesión de no-Dueño**.

La interfaz decide si muestra el enlace «Monitor» con el campo booleano `es_dueno` de `GET /api/v1/users/me` (CT-002). La página `/dashboard/monitor` muestra «no encontrada» si el backend responde 404.

## Autorización (INV-031)
En cada petición, en este orden, y **fail-closed**:
1. `OWNER_EMAIL` vacío o ausente → 404 (ni siquiera se mira la sesión).
2. Sesión verificada (JWT válido, cuenta activa, versión de sesión) → cualquier fallo (sesión ausente o inválida, **BD caída al verificarla**) → 404.
3. `correo_sesion.strip().lower()` y `OWNER_EMAIL.strip().lower()` se comparan con `hmac.compare_digest` sobre sus bytes; distintos → 404.
4. Solo ahora se sabe que es el Dueño: se aplica el límite de frecuencia (429, INV-035; **cuentan también las peticiones que acaban en 405**), se comprueba el método (405 si no es GET) y se leen los contadores (503 si falla **o si la lectura excede el plazo total de 5 s**, `asyncio.wait_for`). Un no-Dueño que «supere» el límite recibe 404, nunca 429.

El camino 404 (no-Dueño, sin sesión) **no tiene límite propio**: riesgo aceptado, anotado en ADR-008.

El 404 tiene el mismo cuerpo que una ruta inexistente (`{"detail": "Not Found"}`); nunca 401/403/503 a quien no esté confirmado como Dueño, y el cuerpo no menciona el Monitor ni al Dueño. El 404 **no lleva `Cache-Control: no-store`** ni ninguna cabecera añadida por el Monitor (CHG-017 §4 pregunta 15). Prueba: se compara byte a byte (cuerpo y cabeceras, salvo `Date`) el 404 del no-Dueño con el de `GET /api/v1/no-existe` y con el de `GET /api/v1/monitor/no-existe`; ambos sin `no-store`.

## Respuesta 200
```json
{
  "generado_en": "2026-11-24T15:00:00Z",
  "contadores": {
    "desde": "2026-11-24",
    "dias": [
      {
        "fecha": "2026-11-24",
        "claude": { "asistente": { "llamadas": 4, "tokens_entrada": 5200, "tokens_salida": 900 },
                    "whatsapp":  { "llamadas": 2, "tokens_entrada": 1800, "tokens_salida": 300 } },
        "brevo_correos_enviados": 3,
        "whatsapp_mensajes": { "enviados": 6, "recibidos": 7 }
      }
    ]
  },
  "plataformas": {
    "railway":   { "estado": "ok", "datos": { }, "actualizado_en": "2026-11-24T14:59:30Z" },
    "anthropic": { "estado": "no_disponible", "datos": null, "actualizado_en": null },
    "meta":      { "estado": "ok", "datos": { }, "actualizado_en": "..." },
    "supabase":  { "estado": "ok", "datos": { }, "actualizado_en": "..." },
    "vercel":    { "estado": "ok", "datos": { }, "actualizado_en": "..." },
    "brevo":     { "estado": "ok", "datos": { }, "actualizado_en": "..." }
  }
}
```
- Claves fijas de primer nivel: `generado_en`, `contadores` (`desde`, `dias`) y `plataformas`; las seis plataformas son `railway`, `anthropic`, `meta`, `supabase`, `vercel` y `brevo`.
- Todas las fechas-instante (`generado_en`, `actualizado_en`, instantes en `datos`) son UTC en ISO-8601 con sufijo `Z` (`YYYY-MM-DDTHH:MM:SSZ`); las fechas de día son `YYYY-MM-DD`.
- `contadores.dias`: solo agregados por día UTC, **ventana de lectura fija de los últimos 30 días** (`VENTANA_DIAS`, incluido hoy) aunque se retengan 90 (INV-036); orden ascendente; solo aparecen los días con al menos un contador. Dentro de un día presente, `claude.asistente` y `claude.whatsapp` están **siempre presentes** con `llamadas`, `tokens_entrada` y `tokens_salida` (ceros si no hubo), y `brevo_correos_enviados` y `whatsapp_mensajes.{enviados,recibidos}` valen 0 si no hubo. La fila marcadora de purga (métrica `purga`) nunca aparece. Sin datos aún → `dias: []`.
- `contadores.desde`: fecha UTC (`YYYY-MM-DD`) del contador más antiguo **conservado** (no se limita a la ventana de 30 días); `null` si no hay ninguno. No hay histórico anterior a la activación.
- `plataformas.<nombre>`: siempre las seis claves. `estado` ∈ `ok` | `no_disponible`. `datos` es un objeto plano que cumple el esquema de la tabla de abajo cuando `ok`, y `null` cuando `no_disponible`. `actualizado_en` = instante (UTC) de la consulta que originó el dato (puede ser de la caché), `null` si no disponible.
- Una plataforma es `no_disponible` si falta su token (`MONITOR_*`) o su id de configuración, si la consulta falla, excede el plazo **total** de 5 s (no solo el de una fase de la conexión), devuelve redirección, una respuesta no válida, un cuerpo de **más de 1 MB** (se descarta al leerlo, también ya descomprimido), o si tras filtrar no queda ningún campo válido. Nunca se devuelve el motivo detallado, un código de la plataforma, un mensaje de error de ella ni parte de una URL (INV-032). Un fallo no afecta a las demás. Los avisos de log incluyen solo un motivo de lista cerrada (p. ej. `http_401`, `graphql_errors`, `json_invalido`, `sin_campos`; nunca cuerpos, mensajes, URLs, cabeceras ni tokens) para diagnóstico; el motivo no sale en la respuesta.
- Nunca aparecen: tokens, correo del Dueño, correos, teléfonos, textos, ids de usuario.

## Esquema de `datos` por plataforma (INV-032)
Regla comprobable: `datos` es un objeto **plano** (sin anidar) cuyas **claves** están en la lista blanca de la plataforma y cuyos **valores** son solo (a) `int` o `float` finitos **no negativos** (nunca `bool`, que en Python es subclase de `int`; nunca negativos, NaN ni infinito), (b) fechas ISO (`YYYY-MM-DD` o instante UTC con `Z`) o (c) cadenas de la lista blanca del campo. Todo lo demás se descarta; si no queda ningún campo, la plataforma es `no_disponible`. Cada campo es opcional: lo que la API no entregue, se omite.

| Plataforma | Campos permitidos (lista blanca) |
|---|---|
| `railway` | `uso_cpu_vcpu_horas` (número), `uso_memoria_gb_horas` (número), `costo_estimado_mes` (número, **US$ gastados en el período de facturación**; = `currentUsage`, valor en caché de Railway), `moneda` (`USD`, solo junto a `costo_estimado_mes`), `creditos_saldo` (número, US$ de créditos prepagados sin usar; = `creditBalance`), `periodo_hasta` (fecha: fin de `billingPeriod` en UTC; si no existe, el fin del mes actual). Se hacen **dos consultas `query` de solo lectura** (misma URL fija y token, en paralelo, plazo total de 5 s): `estimatedUsage` (CPU y memoria) y `project{workspace{customer{currentUsage creditBalance billingPeriod{start end}}}}` (gasto). Si una falla, la otra se muestra; si fallan ambas, `no_disponible`. En la interfaz los US$ no pasan por el conversor de moneda |
| `anthropic` | O bien `estado: no_disponible` (si `MONITOR_ANTHROPIC_ADMIN_KEY` **no empieza por `sk-ant-admin`**, es decir, no es una clave de administración de organización, o la consulta falla), o bien `ok` con **solo** estos campos, cada uno **omitido** si su informe no trajo filas válidas (nunca un 0 inventado): `costo_mes` (número), `moneda` (`USD`), `tokens_entrada_mes` (número), `tokens_salida_mes` (número). Los informes de uso y de costo se procesan por separado: que uno falle no tumba al otro |
| `meta` | `conversaciones_periodo` (número), `periodo_desde` (fecha), `periodo_hasta` (fecha). Es el total de **mensajes facturables del periodo** (día 1 del mes UTC hasta ahora) vía `pricing_analytics` (granularidad `DAILY`, suma de `volume` de los `data_points`; el nombre del campo se conserva por compatibilidad). `conversation_analytics` ya no existe en la API de Meta. Un 200 sin `pricing_analytics` significa 0 mensajes facturables (`ok` con 0, no un fallo); un error HTTP (p. ej. 400) o una forma inválida es `no_disponible` |
| `supabase` | `tamano_bd_bytes` (número), `limite_bd_bytes` (número). **Siempre `no_disponible` por ahora**: la Management API no ofrece un GET de solo lectura con el tamaño de la BD (ADR-008); el cliente solo valida que haya token y nunca consulta |
| `vercel` | Solo `plan` (`gratuito` \| `pro` \| `otro`), leído del equipo. `ancho_banda_bytes` y `limite_ancho_banda_bytes` quedan en la lista blanca pero hoy no se rellenan |
| `brevo` | `creditos_restantes` (número), `enviados_hoy` (número) |

**Campos confirmados al implementar (CHG-017 T4):** los de la tabla describen lo que el código rellena hoy; **la verificación contra las APIs reales con los tokens de producción es manual y está pendiente** (no hay pruebas automáticas contra las plataformas). Lo que no se pueda leer queda `no_disponible`. Cualquier ajuste a esta tabla (campo añadido, renombrado o retirado) se registra aquí en CT-010 **antes del cierre** del cambio y no puede incluir datos personales ni texto libre.

## Errores
| Código | Cuándo |
|---|---|
| 404 | No-Dueño con cualquier método salvo OPTIONS; sin sesión o sesión inválida; BD caída al verificar la sesión; `OWNER_EMAIL` sin configurar (todos indistinguibles entre sí, INV-031/INV-033); además, cualquier usuario (Dueño incluido) y método sobre una ruta inexistente bajo `/monitor/*` |
| 405 | **Solo el Dueño confirmado**, con un método distinto de GET (incluido HEAD) sobre la ruta existente (INV-033); cuenta para el límite |
| 429 | **Solo el Dueño confirmado** excede el límite de frecuencia (INV-035); un no-Dueño nunca recibe 429 |
| 503 | **Solo el Dueño confirmado**, y la BD de Supabase falla al leer los contadores (INV-013). Las plataformas externas **no** producen 503: se marcan `no_disponible` |

## Cabeceras
- `Cache-Control: no-store` **solo** en las respuestas al Dueño confirmado: 200, 405, 429 y 503 (INV-035). El 404 (no-Dueño, sin sesión, BD caída al autorizar, `OWNER_EMAIL` sin configurar) **no** lleva `no-store`: es idéntico al 404 de una ruta inexistente de la API.
- Valores fijos (configuración del servidor, no contrato con el cliente; el Dueño puede cambiarlos, CHG-017 §4 preguntas 6 y 16): caché en memoria de **60 s por plataforma**, **20 peticiones por minuto por Dueño** (cuentan 200, 405 y 429), plazo **total** de **5 s por plataforma** impuesto con `asyncio.wait_for` (no basta el timeout por fase de `httpx`).
- Los **fallos** (`no_disponible`) se cachean **15 s** por plataforma (para no martillear una API caída ni gastar cuota).
- Contadores y plataformas se consultan **en paralelo**. Tiempo máximo de `GET /monitor/resumen` en el peor caso (todas las plataformas lentas): **< 6 s**.

## Variables de entorno (nombres; sin valores)
| Variable | Uso |
|---|---|
| `OWNER_EMAIL` | Correo del Dueño (INV-031) |
| `MONITOR_RAILWAY_TOKEN`, `MONITOR_RAILWAY_PROJECT_ID` | Railway: token y id del proyecto |
| `MONITOR_ANTHROPIC_ADMIN_KEY` | Anthropic: clave de **administración** (debe empezar por `sk-ant-admin`; si no, `no_disponible` sin enviarla) |
| `MONITOR_META_TOKEN`, `MONITOR_META_WABA_ID` | Meta: token y id de la cuenta de WhatsApp Business. La versión de Graph reutiliza `WHATSAPP_GRAPH_VERSION` |
| `MONITOR_SUPABASE_TOKEN` | Supabase: reservado (hoy la plataforma queda siempre `no_disponible`) |
| `MONITOR_VERCEL_TOKEN`, `MONITOR_VERCEL_TEAM_ID` | Vercel: token e id del equipo |
| `MONITOR_BREVO_KEY` | Brevo: clave de API (Brevo no ofrece claves de solo lectura: es de **acceso completo**, ver ADR-008) |

Los ids se validan con formato estricto (`^[A-Za-z0-9_-]{1,64}$`; la versión de Graph con `^v\d{1,2}\.\d{1,2}$`, INV-034). Los
tokens `MONITOR_*` son distintos de los de envío o escritura y se crean con el menor permiso que la plataforma ofrezca;
ambas cosas se verifican por revisión de configuración (INV-032, ADR-008).

## Contadores (escritos por el flujo normal, no por este endpoint)
Entidad «Contador diario» (`02-ENTITIES.md`): fecha UTC, métrica, origen, cantidad; clave única (fecha, métrica, origen); incremento atómico.
**Nombres de métrica fijos** (lista cerrada; cualquier otro se rechaza al escribir):
| Métrica (nombre fijo) | Origen | Se incrementa en |
|---|---|---|
| `claude_llamadas`, `claude_tokens_entrada`, `claude_tokens_salida` | `asistente` / `whatsapp` | `utils/asistente.py::llamar_claude` (`_contar_uso`) |
| `brevo_correos_enviados` | `general` | `utils/email.py::send_verification_email` (solo si Brevo aceptó el envío) |
| `whatsapp_enviados` | `general` | `utils/whatsapp.py::enviar` |
| `whatsapp_recibidos` | `general` | el webhook, **solo** mensajes de números enlazados con firma válida; los de números desconocidos y de firma inválida **no** se cuentan |
| `purga` (marcadora, no es consumo) | `general` | la purga oportunista (ver abajo); nunca se expone |

Tabla con RLS, solo agregados por día, retención de 90 días y un fallo al contar nunca interrumpe el flujo (INV-036).

**Purga (soporta varias instancias):** se borran las filas con `fecha < hoy − 90 días` (UTC). La marca de «última purga» vive en la propia tabla: la fila `(fecha = hoy, métrica = purga, origen = general)`. Al escribir un contador se intenta insertar esa fila; solo quien logra insertarla (la clave única impide que lo logren dos) ejecuta la purga ese día, sin tarea programada ni estado en memoria. Las marcas antiguas se purgan con el mismo criterio.

Cada instancia recuerda en memoria el día del último intento de purga y no vuelve a llamar a la función de purga ese día (la marca en la tabla sigue siendo la que garantiza una sola purga entre instancias). Las escrituras desde código asíncrono (`incrementar_async`) hacen la llamada a Supabase en un hilo para no bloquear el servidor; siguen sin lanzar nunca.
