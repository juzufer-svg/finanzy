# UC-014 — Ver el Monitor de consumos

- **REQ:** F-018 · **Contrato:** CT-010 · **Invariantes:** INV-031 a INV-036 (y INV-012 acotado) · **CHG:** CHG-017 · **ADR:** ADR-008
- **Actor:** Dueño (sesión con el correo de `OWNER_EMAIL`). No confundir con el «propietario del registro» de INV-001.

## Precondiciones
`OWNER_EMAIL` configurada en el servidor, el Dueño con sesión activa y, para cada plataforma que quiera ver, su token
`MONITOR_*` e ids de configuración.

## Flujo principal
1. El Dueño ve el enlace «Monitor» (la interfaz lo muestra solo si `es_dueno` es `true` en `GET /users/me`, CT-002) y abre la página `/dashboard/monitor`.
2. La pantalla pide `GET /api/v1/monitor/resumen` con su sesión normal (sin reautenticar).
3. El servidor comprueba que el correo de la sesión es el del Dueño (INV-031); hasta confirmarlo, cualquier fallo es 404.
4. Ya confirmado, aplica el límite de frecuencia (20/min), lee los contadores propios (Claude, Brevo, WhatsApp, últimos
   30 días) y consulta las seis plataformas con sus tokens, todo en paralelo (caché de 60 s por plataforma, plazo total
   de 5 s por plataforma, fallos en caché 15 s; el resumen responde en < 6 s en el peor caso).
5. Responde con los contadores y el estado de cada plataforma; la pantalla muestra las cifras y marca «no disponible»
   las que no se pudieron leer. No hay botones de acción.
6. Cada tarjeta disponible muestra Plan, Límite, Uso actual y % del límite usado (con barra y aviso escrito «Atención: cerca del
   límite» desde el 80 % y «Límite superado» desde el 100 %). Los límites son constantes de referencia del frontend
   (`LIMITES_PLAN`, al 24 nov 2026) y el uso de WhatsApp es el del mes en curso de Colombia según los contadores propios.
   Las plataformas «no disponible» no muestran estas filas.

## Flujos alternos
- Cualquier otro usuario, sin sesión, sesión inválida, **BD caída al verificar la sesión** o `OWNER_EMAIL` sin
  configurar → 404 fail-closed (indistinguible, con cualquier método salvo OPTIONS, que atiende el middleware CORS);
  la interfaz no muestra el enlace al Monitor si `es_dueno` es `false` y, si se entra por la dirección, la página
  `/dashboard/monitor` muestra «no encontrada» al recibir 404.
- El Dueño usa un método distinto de GET (incluido HEAD) → 405 con `no-store`, sin efectos; cuenta para el límite.
- Subruta inexistente bajo `/monitor/*` → 404 normal para cualquiera, con cualquier método.
- Falta el token de una plataforma, o su API falla, tarda más de 5 s, redirige o devuelve datos no válidos → esa
  plataforma «no disponible»; las demás se muestran.
- Sin contadores todavía → lista vacía («aún sin datos desde la activación»).
- Dueño confirmado y la BD falla al leer contadores → 503 y la pantalla muestra el estado de error con reintento.
- Dueño confirmado que excede 20 peticiones por minuto → 429.
- Un contador no se puede escribir en el flujo normal → se registra un aviso sin datos y el flujo continúa (INV-036).
- Cuenta del Dueño eliminada y correo registrado de nuevo por otra persona → obtiene el acceso al verificarlo
  (riesgo aceptado, ADR-008; mitigación opcional anotada como deuda).
