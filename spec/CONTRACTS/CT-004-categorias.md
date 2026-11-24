# CT-004 — Categorías `/api/v1/categorias`

- **Versión:** v1 · **UC:** UC-005 · **REQ:** F-006
- **Permiso requerido:** sesión vigente (INV-016; errores comunes 401/503 en CT-002). Toda operación por ID verifica al propietario del registro (INV-001).

Cuerpo (POST y PUT): `{ "nombre": "texto 1-100", "icono": "texto ≤ 16 (opcional)", "tipo": "ingreso | gasto" }`
Salida: `{ "id", "usuario_id", "nombre", "icono", "tipo" }`

| Endpoint | Respuesta | Errores propios |
|---|---|---|
| `GET /categorias` | 200 lista; si el usuario no tiene ninguna, se crean y devuelven las 7 por defecto | — |
| `POST /categorias` | 200 categoría creada | 422 |
| `PUT /categorias/{id}` | 200 categoría actualizada | 404 "Categoría no encontrada" |
| `DELETE /categorias/{id}` | 200 `{ "message": "Categoría eliminada" }` | 404; 409 "No se pudo eliminar. Puede tener transacciones asociadas." |

Efectos de eliminar: sus transacciones quedan sin categoría (`ON DELETE SET NULL`) y sus presupuestos se eliminan (`CASCADE`).

## CHG-013 (v1.1) · INV-028
- `POST` y `PUT`: el nombre se guarda sin espacios sobrantes (vacío → 422). Si la persona ya tiene una categoría con
  ese nombre (sin distinguir mayúsculas) y el mismo tipo → **409** «Ya tienes una categoría con ese nombre y tipo.»
- La primera carga crea las categorías por defecto; si dos cargas llegan a la vez, la restricción UNIQUE evita duplicarlas
  y se devuelve lo que quedó guardado.
