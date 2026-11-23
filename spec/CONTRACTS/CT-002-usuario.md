# CT-002 — Usuario `/api/v1/users/me`

- **Versión:** v1.1 (CHG-012: `PUT /users/me` y `POST /users/me/password`, nuevos) · **UC:** UC-009, UC-010 · **REQ:** F-011, F-013, F-014
- **Permiso requerido:** sesión (`Authorization: Bearer <JWT>`). Opera siempre sobre el usuario del token.

| Error común | Cuándo | `detail` |
|---|---|---|
| 401 | Formato incorrecto o token inválido/vencido | "Token inválido" |
| 401 | Sesión cerrada por un cambio de contraseña, o el usuario del token ya no existe (INV-016) | "Tu sesión ya no es válida. Inicia sesión de nuevo." |
| 422 | Sin cabecera `Authorization` | (FastAPI) |
| 503 | No se pudo verificar la sesión porque la base de datos falló | "Servicio no disponible. Intenta de nuevo en unos minutos." |

Estos errores comunes aplican a **todas** las rutas protegidas (CT-002 a CT-006). El frontend cierra la sesión
ante un 401 y no ante un 503.

## `GET /users/me` → 200
Salida: `{ "id", "email", "full_name", "currency" }` (nunca incluye el hash de la contraseña).

## `PUT /users/me/currency` → 200
Entrada: `{ "currency": "USD|EUR|MXN|ARS|COP|CLP" }` · Salida: igual que `GET /users/me`. Otro valor → 422.
Si la base de datos no guardó el cambio → 503 «No se pudo guardar la moneda. Intenta de nuevo en unos minutos.»
(nunca se responde 200 sin haber guardado; el frontend avisa que quedó solo en el navegador).

## `PUT /users/me` → 200 (CHG-012)
Entrada: `{ "full_name": "2-100 caracteres" }` (se quitan espacios repetidos y de los extremos; si quedan < 2 → 422).
Salida: igual que `GET /users/me`. Si la base de datos no guardó el cambio → 503 «No se pudo guardar el cambio. Intenta de nuevo en unos minutos.»

## `POST /users/me/password` → 200 (CHG-012, INV-027)
Entrada: `{ "actual": "1-128", "nueva": "8-128 (INV-018), distinta de la actual" }`.
Salida: `{ "access_token", "token_type", "user_id", "full_name" }` — el proxy de Next.js guarda el token nuevo en la
cookie HttpOnly y lo quita de la respuesta (el navegador recibe `{ "user_id", "full_name" }`, INV-020).
Efectos: guarda el nuevo hash bcrypt y sube `session_version` (el token nuevo usa la versión que devuelve esa misma escritura, sin volver a leer) (cierra las demás sesiones, INV-016); esta sesión sigue con el token nuevo.

| Error | Cuándo | `detail` |
|---|---|---|
| 400 | Contraseña actual incorrecta (cuenta como fallo de login: 5 → bloqueo de 15 min, INV-010). No es 401 para que el frontend no cierre la sesión | «La contraseña actual no es correcta» |
| 422 | Nueva fuera de 8-128 o igual a la actual | «La nueva contraseña debe ser distinta de la actual» / validación |
| 429 | Correo bloqueado por fallos o demasiados intentos desde la IP | «Demasiados intentos fallidos…» / «Demasiadas solicitudes…» |
| 503 | La base de datos falló: no cambia nada ni cierra sesiones | «No se pudo guardar el cambio. Intenta de nuevo en unos minutos.» |

## `DELETE /users/me` → 204
Elimina la cuenta y, por cascada, todas sus categorías, transacciones, presupuestos y metas. Irreversible.
La confirmación (escribir el correo) se exige en la interfaz.
