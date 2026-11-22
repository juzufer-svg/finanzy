# CT-001 — Autenticación `/api/v1/auth/*`

- **Versión:** v1 · **UC:** UC-001, UC-002, UC-003 · **REQ:** F-001, F-002, F-003
- **Permiso requerido:** ninguno (visitante). Todos sujetos a límites por IP (INV-010).
- Errores de validación de formato: **422** (FastAPI). Límite superado: **429** con `detail` legible.
- **Navegador (ADR-005):** el navegador habla con el proxy de Next.js (`/api/v1/*`), nunca con el backend. Toda
  petición que cambia datos lleva `x-finanzy-csrf: 1` (si falta o el `Origin` es ajeno → **403**). En `login` y
  `verify-email` el proxy guarda el token en la cookie HttpOnly y **quita `access_token` y `token_type`** de la
  respuesta. Rutas propias del proxy: `POST /auth/logout` → 204 (borra la cookie) y `POST /auth/adopt`
  `{ "token" }` → 200 con el usuario (migra una sesión antigua de `localStorage`; 401 si no es válida).
  Sin cookie, toda ruta protegida responde **401** «Tu sesión ya no es válida. Inicia sesión de nuevo.»

## `POST /register` → 201
Entrada: `{ "email": "Email", "full_name": "texto 2-100", "password": "texto 8-128" }` (INV-018)
Salida: `{ "status": "pending", "message": "Te enviamos un código de 6 dígitos…" }`

| HTTP | Cuándo | `detail` |
|---|---|---|
| 409 | El correo ya pertenece a una cuenta activa | "El correo ya está registrado" |
| 429 | Límite por IP, o 10 correos/día al destinatario | "Demasiadas solicitudes…" / "Ya enviamos varios códigos…" |

Efectos: crea cuenta pendiente (si no existía); emite código salvo que haya uno de < 60 s.

## `POST /verify-email` → 200
Entrada: `{ "email": "Email", "code": "6 dígitos" }` · Salida: `{ "access_token", "token_type": "bearer", "user_id", "full_name" }`

| HTTP | Cuándo | `detail` |
|---|---|---|
| 400 | Código incorrecto, usado, vencido o invalidado | "Código inválido o expirado" |
| 404 | La cuenta ya no existe | "Usuario no encontrado" |

Efectos: activa la cuenta (INV-007: el código se consume).

## `POST /resend-code` → 200
Entrada: `{ "email": "Email" }` · Salida: `{ "status": "pending", "message": "Si tu cuenta está pendiente de verificación, te enviamos un código…" }`
Misma respuesta exista o no la cuenta (INV-009). Solo envía a cuentas pendientes. 429 como en `/register`.

## `POST /login` → 200
Entrada: `{ "email": "Email", "password": "texto" }`
Salida (activa): `{ "access_token", "token_type": "bearer", "user_id" }`
Salida (pendiente, INV-006): `{ "status": "pending", "message": "Tu cuenta no está verificada…" }` + código (con límites)

| HTTP | Cuándo | `detail` |
|---|---|---|
| 401 | Correo inexistente o contraseña incorrecta | "Credenciales inválidas" |
| 429 | 5 fallos del correo (15 min) o 30 intentos por IP / 10 min | "Demasiados intentos fallidos…" / "Demasiadas solicitudes…" |

## `POST /forgot-password` → 200
Entrada: `{ "email": "Email" }` · Salida: `{ "message": "Si existe una cuenta con ese correo, te enviamos un código…" }`
Misma respuesta siempre (INV-009); los límites por destinatario se aplican en silencio. 429 solo por límite de IP.

## `POST /reset-password` → 200
Entrada: `{ "email": "Email", "code": "6 dígitos", "new_password": "texto 8-128" }`
Salida: `{ "message": "Tu contraseña fue actualizada. Ya puedes iniciar sesión." }`

| HTTP | Cuándo | `detail` |
|---|---|---|
| 400 | Código de reset inválido/vencido o cuenta inexistente | "Código inválido o expirado" |

Efectos: nuevo hash bcrypt, cuenta activa, desbloquea el login del correo y **sube la versión de sesión**:
todas las sesiones abiertas de la cuenta dejan de servir (INV-016).

## Sesión (token de `verify-email` y `login`)
JWT con `sub` (id del usuario), `exp` y `sv` (versión de sesión del usuario al emitirlo). Los tokens
emitidos antes de agregar `sv` valen como versión 0. Ver los errores comunes de las rutas protegidas en CT-002.

## Compatibilidad
Cambios incompatibles requieren nueva versión y ADR. El frontend depende de `status: "pending"` y de `detail` como texto.
