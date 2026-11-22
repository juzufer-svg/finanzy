# CT-002 — Usuario `/api/v1/users/me`

- **Versión:** v1 · **UC:** UC-009, UC-010 · **REQ:** F-011, F-013, F-014
- **Permiso requerido:** sesión (`Authorization: Bearer <JWT>`). Opera siempre sobre el usuario del token.

| Error común | Cuándo | `detail` |
|---|---|---|
| 401 | Sin cabecera, formato incorrecto o token inválido/vencido | "Not authenticated" / "Invalid token" |
| 404 | El usuario del token ya no existe | "User not found" |

## `GET /users/me` → 200
Salida: `{ "id", "email", "full_name", "currency" }` (nunca incluye el hash de la contraseña).

## `PUT /users/me/currency` → 200
Entrada: `{ "currency": "USD|EUR|MXN|ARS|COP|CLP" }` · Salida: igual que `GET /users/me`. Otro valor → 422.

## `DELETE /users/me` → 204
Elimina la cuenta y, por cascada, todas sus categorías, transacciones, presupuestos y metas. Irreversible.
La confirmación (escribir el correo) se exige en la interfaz.
