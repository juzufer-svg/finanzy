# ADR-010 — Estado de autenticación persistente en PostgreSQL (bloqueos de login, códigos y límites de envío)

- **Estado:** propuesta (spec de CHG-020, pendiente de aprobación del dueño; alcance, fail-closed y «los despliegues ya no borran bloqueos ni códigos» ya aprobados por el dueño el 2026-11-24)
- **Fecha:** 2026-11-24 · **Decide:** dueño del proyecto

## Contexto
Hoy los bloqueos de login, los códigos de verificación/restablecimiento y los límites de envío viven en memoria del
proceso (`auth.py::_login_fails` y cuatro `SlidingWindow`; `utils/email.py::_pending_codes`; `core/rate_limit.py`).
Cada despliegue o reinicio los borra y, con más de una instancia, cada una tendría los suyos (REQ-N-002, INV-007,
INV-010). Es la deuda de seguridad más importante señalada por el dueño (BL-014).

**Hallazgo (verificado leyendo el código, CHG-020):** con Supabase configurado, `_pending_codes` guarda los códigos en
claro en memoria y `_login_fails` guarda los bloqueos en memoria. INV-013 dice «nunca se guardan datos en memoria
cuando Supabase está configurado»; su prueba solo cubría `models/plataapp.py`. Por tanto hoy **se incumple su
espíritu** para el estado de autenticación. Este ADR **aclara** INV-013 (alcanza al estado de autenticación) y no
debilita ninguna invariante: INV-007, INV-009 e INV-010 conservan sus números.

## Alternativas evaluadas
| Opción | Pros | Contras |
|---|---|---|
| Dejarlo en memoria (instancia única) | Sin cambios | Los despliegues borran bloqueos y códigos; no escala a 2 instancias; incumple INV-013 |
| Redis / Upstash | Pensado para contadores y TTL | Servicio nuevo, otro secreto y posible costo (REQ-N-006); más superficie |
| Estado en el JWT o en cookie | Sin BD | Un atacante no usa nuestra cookie: no sirve contra fuerza bruta |
| Supabase Auth | Trae límites propios | Reescribe todo el login, sesiones y cambios de contraseña (INV-016): fuera de alcance |
| **Tablas PostgreSQL nuevas + funciones SQL atómicas** (elegida) | Ya existe la BD, costo 0, atomicidad real con bloqueo de fila, mismo patrón que INV-008 e INV-036 | Cada intento añade llamadas a la BD; si la BD cae, no hay login (deseado) |

## Decisión
1. **Tres tablas** con RLS activado **sin políticas**, `revoke all` a `anon`/`authenticated` y funciones `EXECUTE` solo para `service_role` (patrón de `contadores_diarios`):
   - `auth_login_intentos` (`clave` huella HMAC del correo, `fallos`, `ventana_inicio`, `bloqueado_hasta`, `actualizado_en`).
   - `auth_codigos` (`clave` huella del correo, `proposito` = `verify`/`reset`, `codigo_hmac`, `emitido_en`, `expira_en`, `intentos`; clave única `(clave, proposito)`: un código vigente por correo y propósito, INV-007).
   - `auth_limites_eventos` (`clave` huella de `tipo:valor` —IP, correo o `global`—, `ocurrido_en`).
2. **Funciones SQL atómicas** (nombres provisionales; el generador puede ajustarlos sin cambiar el comportamiento):
   - `auth_login_reservar(clave, max=5, ventana_seg=900, bloqueo_seg=900)`: con la fila bloqueada (`FOR UPDATE`/upsert) cuenta el intento **antes** de comprobar la contraseña y devuelve `permitido` o `bloqueado_hasta`. Como mucho 5 intentos por ventana llegan a comprobar la contraseña, aunque lleguen 50 peticiones a la vez (INV-038). Al 5.º intento fallido el bloqueo dura 15 min contados desde ese fallo.
   - `auth_login_reiniciar(clave)`: tras un inicio de sesión correcto, un restablecimiento o un cambio de contraseña.
   - `auth_codigo_guardar(clave, proposito, codigo_hmac, ahora)`: reemplaza el código anterior del mismo propósito.
   - `auth_codigo_verificar(clave, proposito, codigo_hmac, ahora, max=5)`: con la fila bloqueada compara, suma el intento fallido, invalida al 5.º, consume el código al acertar (un solo uso) y devuelve `ok` / `incorrecto` / `invalido`. Solo una de dos verificaciones simultáneas del mismo código puede dar `ok`.
   - `auth_codigo_reciente(clave, proposito, segundos, ahora)`: true si se emitió hace menos de 60 s.
   - `auth_limite_registrar(clave, limite, ventana_seg, ahora)`: ventana **deslizante** exacta como la actual (`SlidingWindow`): con bloqueo por clave (`pg_advisory_xact_lock`), cuenta los eventos de la ventana y solo inserta si no se llegó al límite; devuelve booleano.
   - `auth_borrar_de_cuenta(clave_correo)` (intentos y códigos) y `auth_purgar(ahora)` (filas de más de 30 días; una vez al día entre todas las instancias con una marca en la propia tabla, como en INV-036).
3. **Huellas y secretos (INV-040):** `huella = HMAC-SHA256(k, tipo + ":" + valor_normalizado)` con `k = SHA-256("finanzy-auth-estado:" + SECRET_KEY)`; el correo se normaliza `strip().lower()` (INV-014) y la IP tal como la entrega `client_ip`. El código se guarda como `HMAC-SHA256(k, "codigo:" + proposito + ":" + huella_correo + ":" + codigo)`; nunca en claro, ni en logs (INV-012). Una copia de la BD no basta para sacar códigos ni correos.
4. **Números sin cambio:** 5 fallos de login por correo → bloqueo de 15 min; 5 intentos fallidos por código y 10 min de vigencia; 60 s entre códigos al mismo correo; 10 correos/día por destinatario; 250/día en total; 10 pedidos de código por IP/hora; 30 intentos de credenciales/códigos por IP cada 10 min (INV-007, INV-010).
5. **Fail-closed (INV-039):** toda operación de estado tiene un plazo total de 5 s; si la BD falla o se excede, **503** «Servicio no disponible. Intenta de nuevo en unos minutos.» en login, registro, verificación, reenvío, olvido y restablecimiento de contraseña y cambio de contraseña del perfil, también para los límites por IP. Nunca se concede el paso, nunca se usa memoria con Supabase configurado, y el 503 no depende de si la cuenta existe.
6. **Sin enumeración (INV-009):** `forgot-password` y `resend-code` ejecutan las **mismas** llamadas a la BD de estado exista o no la cuenta (para una cuenta inexistente, o activa en `resend-code`, se guarda un código señuelo aleatorio que nunca se envía); la respuesta, el código HTTP y los fallos son idénticos. El envío del correo va en segundo plano como hoy. Riesgo residual aceptado: diferencias de milisegundos; queda cubierto por una prueba que compara las llamadas a la BD, no los tiempos.
7. **Login con cuenta inexistente** sigue contando como fallo (no revela la existencia), y un inicio de sesión correcto reinicia el contador de ese correo.
8. **Modo demo (sin Supabase):** el almacén en memoria actual se conserva **solo fuera de producción**; en producción sin Supabase las rutas de autenticación responden 503 (INV-041, con el mismo criterio de `test_inv013_en_produccion_sin_supabase_no_se_guarda_en_memoria` de los contadores).
9. **Baja de cuenta (REQ-F-013):** `DELETE /users/me` borra de las tablas de intentos y códigos las filas del correo (por huella) después de borrar al usuario; si esa limpieza falla se registra un aviso sin datos y la baja no se revierte (las filas son huellas y se purgan a los 30 días). Los eventos de límites no se borran (evitan reiniciar el tope de 10 correos/día re-registrando el correo).
10. **Fuera de alcance (deuda BL-040):** los limitadores en memoria del asistente (INV-024), de WhatsApp (INV-030 y los intentos del código de enlace) y del Monitor (INV-035) siguen en memoria porque protegen costos y no la autenticación.

## Consecuencias
- Positivas: bloqueos, códigos y topes sobreviven despliegues y reinicios; seguro con varias instancias; atomicidad frente a peticiones paralelas; códigos y correos no quedan en claro en respaldos; INV-013 queda cubierta y comprobable.
- Negativas / deuda aceptada: cada login añade hasta 3 llamadas a la BD (REQ-N-017); si la BD de estado cae, no hay registro ni login (ya era imposible sin la BD de usuarios); rotar `SECRET_KEY` borra bloqueos y códigos pendientes (hoy rotarla ya cierra todas las sesiones); en el despliegue de transición los códigos pendientes en memoria se pierden.
- **Orden de despliegue (obligatorio):** ejecutar `backend/sql/2026-11-24_auth_persistente.sql` en Supabase **antes** de desplegar el backend; sin las tablas todo el login respondería 503. Sin variables de entorno nuevas ni costo adicional (REQ-N-006).
- Impacto en spec, código y pruebas: INV-037 a INV-041; aclaraciones en INV-007/009/010/013; CT-001 (503); `backend/tests/test_auth_persistente.py`; `backend/sql/pruebas/07_comprobar_auth_persistente.sql` y concurrencia real en `probar.sh` (CI, job «Migraciones SQL»); `conftest.py` reinicia el almacén de pruebas; las pruebas existentes de límites y códigos conservan sus números y se adaptan al nuevo almacén.
