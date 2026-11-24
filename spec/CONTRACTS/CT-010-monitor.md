# CT-010 — Monitor del dueño `/api/v1/monitor`

- **Versión:** v1 (CHG-017) · **UC:** UC-014 · **REQ:** F-018 · **ADR:** ADR-008 · **INV:** INV-031 a INV-036
- Solo lectura. Una única ruta. Errores comunes 401/503 de sesión (CT-002) **no** se usan aquí: ver «Errores».

## Endpoint
| Endpoint | Entrada | Respuesta |
|---|---|---|
| `GET /monitor/resumen` | Sesión (cookie → `Authorization`, igual que el resto de la API). Sin parámetros | 200 con el objeto de abajo, solo si el correo de la sesión es el de `OWNER_EMAIL` (INV-031) |

Cualquier otro método sobre `/monitor/*` no ejecuta nada (405 o 404, INV-033). No existen rutas de escritura ni de acciones.

## Autorización (INV-031)
En cada petición: sesión verificada (JWT válido, cuenta activa) y `correo_sesion.strip().lower() == OWNER_EMAIL.strip().lower()`.
Sin `OWNER_EMAIL` (vacío o ausente) → siempre 404. Sin sesión, sesión inválida o correo distinto → **404** con el mismo
cuerpo que una ruta inexistente (`{"detail": "Not Found"}`); nunca 401/403, y el cuerpo no menciona el Monitor ni al dueño.

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
- `contadores.dias`: solo agregados por día UTC desde la activación, hasta 90 días (INV-036); orden ascendente; sin histórico anterior. Sin datos aún → `dias: []`.
- `plataformas.<nombre>`: siempre las seis claves. `estado` ∈ `ok` | `no_disponible`. `datos` es un objeto de **cifras agregadas** de consumo (uso, cuota, créditos, límites; números y fechas) cuando `ok`, y `null` cuando `no_disponible`. `actualizado_en` = instante (UTC) de la consulta que originó el dato (puede ser de la caché), `null` si no disponible.
- Una plataforma es `no_disponible` si falta su token `MONITOR_*_TOKEN` o su id de configuración, si la consulta falla, excede el tiempo máximo, devuelve redirección o una respuesta no válida. Nunca se devuelve el motivo detallado, un código de la plataforma, un mensaje de error de ella ni parte de una URL (INV-032). Un fallo no afecta a las demás.
- La forma exacta de `datos` por plataforma depende de lo que ofrezca cada API con el menor permiso disponible y se define en la tarea de implementación sin añadir campos con datos personales (ver CHG-017 §4).
- Nunca aparecen: tokens, correo del dueño, correos, teléfonos, textos, ids de usuario.

## Errores
| Código | Cuándo |
|---|---|
| 404 | Cualquier persona que no sea el dueño, sin sesión o con sesión inválida, o `OWNER_EMAIL` sin configurar (indistinguibles entre sí) |
| 429 | Se excede el límite de frecuencia del dueño (INV-035) |
| 503 | La base de datos de Supabase falla al leer los contadores (INV-013). Las plataformas externas **no** producen 503: se marcan `no_disponible` |

## Cabeceras
- `Cache-Control: no-store` en toda respuesta de `/monitor/*`, también en los 404 y 429 (INV-035).
- Consultas externas con caché corta en memoria del servidor y límite de frecuencia; valores por defecto **propuestos**: caché de 60 s por plataforma y 20 peticiones por minuto por dueño (pendiente de confirmar, CHG-017 §4 pregunta 6). Son configuración, no contrato con el cliente.

## Variables de entorno (nombres; sin valores)
`OWNER_EMAIL`, `MONITOR_RAILWAY_TOKEN`, `MONITOR_ANTHROPIC_TOKEN`, `MONITOR_META_TOKEN`, `MONITOR_SUPABASE_TOKEN`,
`MONITOR_VERCEL_TOKEN`, `MONITOR_BREVO_TOKEN` y los ids de configuración que requiera cada plataforma (proyecto,
servicio, organización, cuenta; validados con formato estricto, INV-034). Los tokens `MONITOR_*` son distintos de los de
envío o escritura (INV-032).

## Contadores (escritos por el flujo normal, no por este endpoint)
| Métrica | Se incrementa en |
|---|---|
| Claude: llamadas, tokens de entrada y salida, por origen `asistente` / `whatsapp` | `utils/asistente.py::llamar_claude` |
| Brevo: correos enviados con éxito | `utils/email.py::send_verification_email` (solo si Brevo aceptó el envío) |
| WhatsApp: mensajes enviados y recibidos | `utils/whatsapp.py::enviar` y el webhook (mensajes procesados de Meta) |

Tabla con RLS, solo agregados por día, purga a los 90 días, y un fallo al contar nunca interrumpe el flujo (INV-036).
