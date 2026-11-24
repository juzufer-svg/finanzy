# CT-010 — Monitor del Dueño `/api/v1/monitor`

- **Versión:** v1 (CHG-017) · **UC:** UC-014 · **REQ:** F-018 · **ADR:** ADR-008 · **INV:** INV-031 a INV-036
- Solo lectura. Una única ruta. Errores comunes 401/503 de sesión (CT-002) **no** se usan aquí: ver «Errores».
- «Dueño» = actor definido en el glosario (no el «propietario del registro» de INV-001).

## Endpoint
| Endpoint | Entrada | Respuesta |
|---|---|---|
| `GET /monitor/resumen` | Sesión (cookie → `Authorization`, igual que el resto de la API). Sin parámetros | 200 con el objeto de abajo, solo si el correo de la sesión es el de `OWNER_EMAIL` (INV-031) |

No existen rutas de escritura ni de acciones. Regla por método sobre `/monitor/*` (INV-033):
- **No-Dueño** (sin sesión, sesión inválida o cualquier usuario) con **cualquier** método (GET, POST, PUT, PATCH, DELETE, OPTIONS…) y sobre cualquier subruta de `/monitor/*` → **404 idéntico** al de una ruta inexistente (mismo cuerpo y mismas cabeceras).
- **Dueño** con un método distinto de GET sobre una ruta del Monitor → **405**, sin ejecutar nada.

## Autorización (INV-031)
En cada petición, en este orden, y **fail-closed**:
1. `OWNER_EMAIL` vacío o ausente → 404.
2. Sesión verificada (JWT válido, cuenta activa, versión de sesión) → cualquier fallo (sesión ausente o inválida, **BD caída al verificarla**) → 404.
3. `correo_sesion.strip().lower()` y `OWNER_EMAIL.strip().lower()` se comparan con `hmac.compare_digest` sobre sus bytes; distintos → 404.
4. Solo ahora se sabe que es el Dueño: se aplica el límite de frecuencia (429, INV-035) y se leen los contadores (503 si falla).

El 404 tiene el mismo cuerpo que una ruta inexistente (`{"detail": "Not Found"}`); nunca 401/403/503 a quien no esté confirmado como Dueño, y el cuerpo no menciona el Monitor ni al Dueño. Prueba: se compara byte a byte (cuerpo y cabeceras, salvo `Date`) el 404 del no-Dueño con el de `GET /api/v1/monitor/no-existe`, y el cuerpo con el de `GET /api/v1/no-existe`.

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
- `contadores.dias`: solo agregados por día UTC, **ventana fija de los últimos 30 días** (incluido hoy) aunque se retengan 90 (INV-036); orden ascendente; solo aparecen los días con al menos un contador (las métricas ausentes de un día presente valen 0). Sin datos aún → `dias: []`.
- `contadores.desde`: fecha UTC (`YYYY-MM-DD`) del contador más antiguo **conservado** (no se limita a la ventana de 30 días); `null` si no hay ninguno. No hay histórico anterior a la activación.
- `plataformas.<nombre>`: siempre las seis claves. `estado` ∈ `ok` | `no_disponible`. `datos` es un objeto plano que cumple el esquema de la tabla de abajo cuando `ok`, y `null` cuando `no_disponible`. `actualizado_en` = instante (UTC) de la consulta que originó el dato (puede ser de la caché), `null` si no disponible.
- Una plataforma es `no_disponible` si falta su token `MONITOR_*_TOKEN` o su id de configuración, si la consulta falla, excede los 5 s, devuelve redirección, una respuesta no válida, o si tras filtrar no queda ningún campo válido. Nunca se devuelve el motivo detallado, un código de la plataforma, un mensaje de error de ella ni parte de una URL (INV-032). Un fallo no afecta a las demás.
- Nunca aparecen: tokens, correo del Dueño, correos, teléfonos, textos, ids de usuario.

## Esquema de `datos` por plataforma (INV-032)
Regla comprobable: `datos` es un objeto **plano** (sin anidar) cuyas **claves** están en la lista blanca de la plataforma y cuyos **valores** son solo (a) números finitos, (b) fechas ISO (`YYYY-MM-DD` o instante UTC) o (c) cadenas de la lista blanca del campo. Todo lo demás se descarta; si no queda ningún campo, la plataforma es `no_disponible`. Cada campo es opcional: lo que la API no entregue, se omite.

| Plataforma | Campos permitidos (lista blanca) |
|---|---|
| `railway` | `costo_estimado_mes` (número), `uso_cpu_vcpu_horas` (número), `uso_memoria_gb_horas` (número), `moneda` (`USD`), `periodo_hasta` (fecha) |
| `anthropic` | `no_disponible` salvo que `MONITOR_ANTHROPIC_TOKEN` sea una clave de administración (cuenta de organización): entonces `costo_mes` (número), `moneda` (`USD`), `tokens_entrada_mes` (número), `tokens_salida_mes` (número) |
| `meta` | `conversaciones_periodo` (número), `periodo_desde` (fecha), `periodo_hasta` (fecha) |
| `supabase` | `tamano_bd_bytes` (número), `limite_bd_bytes` (número) |
| `vercel` | `plan` (`gratuito` \| `pro` \| `otro`), `ancho_banda_bytes` (número), `limite_ancho_banda_bytes` (número) |
| `brevo` | `creditos_restantes` (número), `enviados_hoy` (número) |

**Los campos exactos se confirman contra cada API al implementar** (con el token del menor permiso que la plataforma ofrezca). Lo que no se pueda leer queda `no_disponible`. Cualquier ajuste a esta tabla (campo añadido, renombrado o retirado) se registra aquí en CT-010 **antes del cierre** del cambio y no puede incluir datos personales ni texto libre.

## Errores
| Código | Cuándo |
|---|---|
| 404 | No-Dueño con cualquier método; sin sesión o sesión inválida; BD caída al verificar la sesión; `OWNER_EMAIL` sin configurar (todos indistinguibles entre sí, INV-031/INV-033) |
| 405 | **Solo el Dueño confirmado**, con un método distinto de GET (INV-033) |
| 429 | **Solo el Dueño confirmado** excede el límite de frecuencia (INV-035) |
| 503 | **Solo el Dueño confirmado**, y la BD de Supabase falla al leer los contadores (INV-013). Las plataformas externas **no** producen 503: se marcan `no_disponible` |

## Cabeceras
- `Cache-Control: no-store` en toda respuesta de `/monitor/*` (200, 404, 405, 429, 503) (INV-035).
- Valores fijos (configuración del servidor, no contrato con el cliente; el Dueño puede cambiarlos, CHG-017 §4 pregunta 6): caché en memoria de **60 s por plataforma**, **20 peticiones por minuto por Dueño**, timeout de **5 s por plataforma** (las plataformas se consultan en paralelo).

## Variables de entorno (nombres; sin valores)
`OWNER_EMAIL`, `MONITOR_RAILWAY_TOKEN`, `MONITOR_ANTHROPIC_TOKEN`, `MONITOR_META_TOKEN`, `MONITOR_SUPABASE_TOKEN`,
`MONITOR_VERCEL_TOKEN`, `MONITOR_BREVO_TOKEN` y los ids de configuración que requiera cada plataforma (proyecto,
servicio, organización, cuenta; validados con formato estricto, INV-034). Los tokens `MONITOR_*` son distintos de los de
envío o escritura y se crean con el menor permiso que la plataforma ofrezca; ambas cosas se verifican por revisión de
configuración (INV-032, ADR-008). Los nombres exactos de los ids se fijan al implementar y se registran aquí.

## Contadores (escritos por el flujo normal, no por este endpoint)
Entidad «Contador diario» (`02-ENTITIES.md`): fecha UTC, métrica, origen, cantidad; clave única (fecha, métrica, origen); incremento atómico.
| Métrica | Origen | Se incrementa en |
|---|---|---|
| Claude: llamadas, tokens de entrada y de salida | `asistente` / `whatsapp` | `utils/asistente.py::llamar_claude` |
| Brevo: correos enviados con éxito | `general` | `utils/email.py::send_verification_email` (solo si Brevo aceptó el envío) |
| WhatsApp: mensajes enviados | `general` | `utils/whatsapp.py::enviar` |
| WhatsApp: mensajes recibidos | `general` | el webhook, **solo** mensajes de números enlazados con firma válida; los de números desconocidos y de firma inválida **no** se cuentan |

Tabla con RLS, solo agregados por día, retención de 90 días con purga oportunista al escribir (como mucho una vez al
día, sin tarea programada), y un fallo al contar nunca interrumpe el flujo (INV-036).
