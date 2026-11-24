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
- Nuevo actor **Dueño**: quien inicia sesión con el correo de `OWNER_EMAIL` (variable de entorno, sin escribirlo en el
  código). Su único privilegio es ver el Monitor. Se valida en el servidor en cada petición; a los demás, 404;
  sin `OWNER_EMAIL`, se niega a todos (INV-031).
- INV-012 y REQ-N-003 se acotan: el Monitor no es un endpoint de diagnóstico y tampoco expone secretos (INV-032).
- Solo lectura (GET). Sin acciones sobre las plataformas (INV-033).
- Contadores propios en Supabase, agregados por día, sin datos personales, desde la activación y con retención de
  90 días; su escritura nunca rompe el flujo principal (INV-036).
- Lectura de las seis plataformas con tokens **propios** `MONITOR_*_TOKEN`, distintos de los de envío o escritura y con
  el menor permiso disponible. Algunas plataformas no ofrecen tokens de solo lectura (p. ej. Anthropic pide clave de
  administración y cuenta de organización): se acepta el menor permiso disponible y lo que no se pueda leer se muestra
  «no disponible» (aprobado, pregunta 2).
- URLs de proveedores fijas en el código, ids solo de configuración, sin redirecciones, con timeout (INV-034); caché
  corta, límite de frecuencia y `Cache-Control: no-store` (INV-035).
- Basta la sesión normal del dueño, sin reautenticar (aprobado, pregunta 4).
- El acceso se concede por correo verificado: si se elimina la cuenta del dueño y otra persona registra ese correo y
  lo verifica, obtendría el acceso. Riesgo aceptado por el dueño (pregunta 5).

## Consecuencias
- Nuevas variables en Railway: `OWNER_EMAIL`, `MONITOR_*_TOKEN` e ids de configuración (CT-010). Nueva migración en
  `backend/sql/` para la tabla de contadores (con RLS).
- Si falta un token, esa plataforma aparece «no disponible»; el resto sigue funcionando.
- Los tokens del Monitor son secretos adicionales: deben crearse con el mínimo permiso y rotarse si se filtran.
- Sin costo adicional (planes gratuitos, REQ-N-006); cualquier plataforma que exija plan de pago para su API se
  muestra «no disponible» y se avisa al dueño antes de pagar.
