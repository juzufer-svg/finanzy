# CT-002 — Usuario `/api/v1/users/me`

- **Versión:** v1 · **UC:** UC-009, UC-010 · **REQ:** F-011, F-013, F-014
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

## `DELETE /users/me` → 204
Elimina la cuenta y, por cascada, todas sus categorías, transacciones, presupuestos y metas. Irreversible.
La confirmación (escribir el correo) se exige en la interfaz.
