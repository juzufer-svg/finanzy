# UC-014 — Ver el Monitor de consumos

- **REQ:** F-018 · **Contrato:** CT-010 · **Invariantes:** INV-031 a INV-036 (y INV-012 acotado) · **CHG:** CHG-017 · **ADR:** ADR-008
- **Actor:** Dueño (sesión con el correo de `OWNER_EMAIL`).

## Precondiciones
`OWNER_EMAIL` configurada en el servidor, el dueño con sesión activa y, para cada plataforma que quiera ver, su token
`MONITOR_*_TOKEN` e ids de configuración.

## Flujo principal
1. El dueño abre la página «Monitor».
2. La pantalla pide `GET /api/v1/monitor/resumen` con su sesión normal (sin reautenticar).
3. El servidor comprueba que el correo de la sesión es el del dueño (INV-031).
4. Lee los contadores propios (Claude, Brevo, WhatsApp, por día) y consulta las seis plataformas con sus tokens de
   solo lectura (con caché corta y tiempo máximo).
5. Responde con los contadores y el estado de cada plataforma; la pantalla muestra las cifras y marca «no disponible»
   las que no se pudieron leer. No hay botones de acción.

## Flujos alternos
- Cualquier otro usuario, o sin sesión, o `OWNER_EMAIL` sin configurar → 404; la interfaz no muestra el enlace al
  Monitor a quien no es dueño y, si se entra por la dirección, muestra «no encontrada».
- Falta el token de una plataforma, o su API falla, tarda o redirige → esa plataforma «no disponible»; las demás se muestran.
- Sin contadores todavía → lista vacía («aún sin datos desde la activación»).
- La base de datos falla al leer contadores → 503 y la pantalla muestra el estado de error con reintento.
- Demasiadas consultas seguidas → 429.
- Un contador no se puede escribir en el flujo normal → se registra un aviso sin datos y el flujo continúa (INV-036).
- Cuenta del dueño eliminada y correo registrado de nuevo por otra persona → obtiene el acceso al verificarlo
  (riesgo aceptado, ADR-008).
