# UC-014 — Ver el Monitor de consumos

- **REQ:** F-018 · **Contrato:** CT-010 · **Invariantes:** INV-031 a INV-036 (y INV-012 acotado) · **CHG:** CHG-017 · **ADR:** ADR-008
- **Actor:** Dueño (sesión con el correo de `OWNER_EMAIL`). No confundir con el «propietario del registro» de INV-001.

## Precondiciones
`OWNER_EMAIL` configurada en el servidor, el Dueño con sesión activa y, para cada plataforma que quiera ver, su token
`MONITOR_*_TOKEN` e ids de configuración.

## Flujo principal
1. El Dueño abre la página «Monitor».
2. La pantalla pide `GET /api/v1/monitor/resumen` con su sesión normal (sin reautenticar).
3. El servidor comprueba que el correo de la sesión es el del Dueño (INV-031); hasta confirmarlo, cualquier fallo es 404.
4. Ya confirmado, aplica el límite de frecuencia (20/min), lee los contadores propios (Claude, Brevo, WhatsApp, últimos
   30 días) y consulta las seis plataformas con sus tokens (caché de 60 s por plataforma, timeout de 5 s).
5. Responde con los contadores y el estado de cada plataforma; la pantalla muestra las cifras y marca «no disponible»
   las que no se pudieron leer. No hay botones de acción.

## Flujos alternos
- Cualquier otro usuario, sin sesión, sesión inválida, **BD caída al verificar la sesión** o `OWNER_EMAIL` sin
  configurar → 404 fail-closed (indistinguible, con cualquier método); la interfaz no muestra el enlace al Monitor a
  quien no es Dueño y, si se entra por la dirección, muestra «no encontrada».
- El Dueño usa un método distinto de GET → 405, sin efectos.
- Falta el token de una plataforma, o su API falla, tarda más de 5 s, redirige o devuelve datos no válidos → esa
  plataforma «no disponible»; las demás se muestran.
- Sin contadores todavía → lista vacía («aún sin datos desde la activación»).
- Dueño confirmado y la BD falla al leer contadores → 503 y la pantalla muestra el estado de error con reintento.
- Dueño confirmado que excede 20 peticiones por minuto → 429.
- Un contador no se puede escribir en el flujo normal → se registra un aviso sin datos y el flujo continúa (INV-036).
- Cuenta del Dueño eliminada y correo registrado de nuevo por otra persona → obtiene el acceso al verificarlo
  (riesgo aceptado, ADR-008; mitigación opcional anotada como deuda).
