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
Salida: `{ "id", "email", "full_name", "currency", "es_dueno" }` (nunca incluye el hash de la contraseña).
`es_dueno` (CHG-017, booleano): `true` solo si el correo de la sesión coincide con `OWNER_EMAIL` (misma comparación que INV-031: `strip().lower()` y `hmac.compare_digest`). Es `false` por defecto, si `OWNER_EMAIL` está vacío o ausente y si la comprobación falla por cualquier motivo (nunca provoca un error en `/users/me`). Solo informa a cada usuario sobre sí mismo; jamás devuelve el correo del dueño. La interfaz lo usa solo para mostrar u ocultar el enlace «Monitor»; la autorización real sigue en el backend (CT-010). Las salidas «igual que `GET /users/me`» de los `PUT` también lo incluyen.

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
Efectos: guarda el nuevo hash bcrypt y sube `session_version` (el token nuevo usa la versión que devuelve esa misma escritura, sin volver a leer) (cierra las demás sesiones, INV-016); esta sesión sigue con el token nuevo. **Antes** de cambiarla desconecta WhatsApp (CHG-014); si eso falla responde 503 y no cambia nada.

| Error | Cuándo | `detail` |
|---|---|---|
| 400 | Contraseña actual incorrecta (cuenta como fallo de login: 5 → bloqueo de 15 min, INV-010). No es 401 para que el frontend no cierre la sesión | «La contraseña actual no es correcta» |
| 422 | Nueva fuera de 8-128 o igual a la actual | «La nueva contraseña debe ser distinta de la actual» / validación |
| 429 | Correo bloqueado por fallos o demasiados intentos desde la IP | «Demasiados intentos fallidos…» / «Demasiadas solicitudes…» |
| 503 | La base de datos falló: no cambia nada ni cierra sesiones | «No se pudo guardar el cambio. Intenta de nuevo en unos minutos.» |

## `DELETE /users/me` → 204
Elimina la cuenta y, por cascada, todas sus categorías, transacciones, presupuestos y metas. Irreversible.
La confirmación (escribir el correo) se exige en la interfaz.

**Notas de CHG-019 y CHG-020 sobre `DELETE /users/me`:** el borrado en cascada incluye las cuentas de dinero y las transferencias del usuario (INV-021, INV-050; el disparador de saldo no bloquea la cascada) y, después del borrado, se limpian sus intentos de login y códigos pendientes por huella (INV-040; si la limpieza falla, la baja no se revierte). `POST /users/me/password` puede responder **503** si falla el estado de autenticación (CT-001, INV-039).
