# CT-001 — Autenticación `/api/v1/auth/*`

- **Versión:** v1.1 (CHG-020, ciclo 2: 503 por fallo del estado de autenticación o de la tabla de usuarios; ventana de 24 h de los 5 fallos; `resend-code` ahora responde igual —incluido el 429— exista o no la cuenta; sin otros cambios de cuerpo ni de códigos) · **UC:** UC-001, UC-002, UC-003 · **REQ:** F-001, F-002, F-003 · **ADR:** ADR-010 · **INV:** INV-037 a INV-041
- **Permiso requerido:** ninguno (visitante). Todos sujetos a límites por IP (INV-010).
- Errores de validación de formato: **422** (FastAPI). Límite superado: **429** con `detail` legible.
- **Navegador (ADR-005):** el navegador habla con el proxy de Next.js (`/api/v1/*`), nunca con el backend. Toda
  petición que cambia datos lleva `x-finanzy-csrf: 1` (si falta o el `Origin` es ajeno → **403**). En `login` y
  `verify-email` el proxy guarda el token en la cookie HttpOnly y **quita `access_token` y `token_type`** de la
  respuesta. Rutas propias del proxy: `POST /auth/logout` → 204 (borra la cookie) y `POST /auth/adopt`
  `{ "token" }` → 200 con el usuario (migra una sesión antigua de `localStorage`; 401 si no es válida; 204 sin
  cambios si ya hay una sesión en la cookie; 502/503 si el backend no responde, y el navegador reintenta después).
  Un 401 de `auth/*` (p. ej. contraseña mala) no borra la cookie. El proxy reenvía `Content-Type` del backend
  (y, **solo** en `exportaciones/*`, también `Content-Disposition`, CHG-018) y depende de Vercel para la IP real (`x-forwarded-for`).
  Sin cookie, toda ruta protegida responde **401** «Tu sesión ya no es válida. Inicia sesión de nuevo.»
  (CHG-018: el proxy ya entrega el cuerpo como bytes y pone `Cache-Control: no-store` a toda respuesta; para las descargas de
  `exportaciones/*`, CT-011, solo falta reenviar `Content-Disposition` y declarar `maxDuration = 10`; las demás rutas siguen igual.)
- **Estado de autenticación persistente (CHG-020, ADR-010):** los bloqueos de login, los códigos y los límites de envío
  y de intentos viven en PostgreSQL (INV-037) y sobreviven a despliegues. **Nuevo error común a `register`, `verify-email`,
  `resend-code`, `login`, `forgot-password`, `reset-password` y `POST /users/me/password` (CT-002): 503**
  «Servicio no disponible. Intenta de nuevo en unos minutos.» cuando la BD de estado falla o tarda más de 5 s (fail-closed,
  INV-039; también para los límites por IP y también si falla **solo** la lectura de la tabla de usuarios, que antes se confundía
  con «no existe»). Nunca devuelve 200/400/401/404 en ese caso y es idéntico exista o no la cuenta
  (INV-009). Los números de los límites y los textos de 429/400/401 **no cambian** (única precisión: los 5 fallos de login
  se cuentan en una **ventana de 24 h** desde el primer fallo, INV-010). En producción sin Supabase: 503.

## `POST /register` → 201
Entrada: `{ "email": "Email", "full_name": "texto 2-100", "password": "texto 8-128" }` (INV-018)
Salida: `{ "status": "pending", "message": "Te enviamos un código de 6 dígitos…" }`

| HTTP | Cuándo | `detail` |
|---|---|---|
| 409 | El correo ya pertenece a una cuenta activa | "El correo ya está registrado" |
| 429 | Límite por IP, o 10 correos/día al destinatario | "Demasiadas solicitudes…" / "Ya enviamos varios códigos…" |

Efectos: crea cuenta pendiente (si no existía); emite código salvo que haya uno de < 60 s (una sola operación atómica de la BD, INV-038).

## `POST /verify-email` → 200
Entrada: `{ "email": "Email", "code": "6 dígitos" }` · Salida: `{ "access_token", "token_type": "bearer", "user_id", "full_name" }`
Orden (CHG-020): límite por IP → leer el usuario (si la lectura falla, 503 sin consumir el código) → verificar y consumir el código.

| HTTP | Cuándo | `detail` |
|---|---|---|
| 400 | Código incorrecto, usado, vencido o invalidado | "Código inválido o expirado" |
| 404 | La cuenta ya no existe | "Usuario no encontrado" |

Efectos: activa la cuenta (INV-007: el código se consume).

## `POST /resend-code` → 200
Entrada: `{ "email": "Email" }` · Salida: `{ "status": "pending", "message": "Si tu cuenta está pendiente de verificación, te enviamos un código…" }`
Misma respuesta exista o no la cuenta (INV-009). Solo **envía** a cuentas pendientes, pero **ejecuta y cuenta igual** para cualquier correo (inexistente, activo o pendiente): una sola emisión de código con los mismos 60 s y los mismos topes de 10/día por destinatario y 250 globales; para una cuenta inexistente o ya activa el código es un señuelo que no se envía y que no puede verificarse. **429 «Ya enviamos varios códigos…» al alcanzar un tope, igual para todos los correos** (CHG-020 cierra un hueco previo: hoy solo respondía 429 para cuentas pendientes, lo que enumeraba cuentas pendientes). 429 por IP como en `/register`.

## `POST /login` → 200
Entrada: `{ "email": "Email", "password": "texto" }`
Salida (activa): `{ "access_token", "token_type": "bearer", "user_id" }`
Salida (pendiente, INV-006): `{ "status": "pending", "message": "Tu cuenta no está verificada…" }` + código (con límites)

| HTTP | Cuándo | `detail` |
|---|---|---|
| 401 | Correo inexistente o contraseña incorrecta (con un correo inexistente se ejecuta igual la comprobación bcrypt contra un hash señuelo, M-5) | "Credenciales inválidas" |
| 429 | 5 fallos del correo dentro de una ventana de 24 h → bloqueo de 15 min, o 30 intentos por IP / 10 min | "Demasiados intentos fallidos…" / "Demasiadas solicitudes…" |

El intento se **reserva** antes de comprobar la contraseña (INV-038): con peticiones simultáneas solo 5 llegan a comprobarla y el resto recibe 429. Si la 5.ª reserva acierta, inicia sesión. Riesgo aceptado (M-6): quien conozca un correo puede bloquearlo 15 min; `reset-password` lo desbloquea.

## `POST /forgot-password` → 200
Entrada: `{ "email": "Email" }` · Salida: `{ "message": "Si existe una cuenta con ese correo, te enviamos un código…" }`
Misma respuesta siempre (INV-009); los topes por destinatario y global se aplican **en silencio** (200 igual) y se ejecutan y cuentan igual exista o no la cuenta (código señuelo, sin envío). **429 solo por el límite de IP** (corrige la ambigüedad anterior entre «en silencio» y «429 como /register»: en `forgot-password` el único 429 es el de IP; en `resend-code` también el de los topes).

## `POST /reset-password` → 200
Entrada: `{ "email": "Email", "code": "6 dígitos", "new_password": "texto 8-128" }`
Salida: `{ "message": "Tu contraseña fue actualizada. Ya puedes iniciar sesión." }`
Efectos: desconecta WhatsApp (antes del cambio), cambia la contraseña y cierra todas las sesiones (INV-016).

| HTTP | Cuándo | `detail` |
|---|---|---|
| 400 | Código de reset inválido/vencido o cuenta inexistente (el usuario se lee antes de consumir el código; si la lectura falla, 503) | "Código inválido o expirado" |
| 503 | No se pudo desconectar WhatsApp antes del cambio (fallo de la BD): no se cambia nada (CHG-014, INV-016) | "Servicio no disponible. Intenta de nuevo en unos minutos." |

Efectos: nuevo hash bcrypt, cuenta activa, desbloquea el login del correo y **sube la versión de sesión**:
todas las sesiones abiertas de la cuenta dejan de servir (INV-016).

## Sesión (token de `verify-email` y `login`)
JWT con `sub` (id del usuario), `exp` y `sv` (versión de sesión del usuario al emitirlo). Los tokens
emitidos antes de agregar `sv` valen como versión 0. Ver los errores comunes de las rutas protegidas en CT-002.

## Compatibilidad
Cambios incompatibles requieren nueva versión y ADR. El frontend depende de `status: "pending"` y de `detail` como texto.
