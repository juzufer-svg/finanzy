# CT-006 — Metas `/api/v1/metas`

- **Versión:** v1.1 (CHG-019 fase c: `cuenta_id` opcional en el abono) · **UC:** UC-007 · **REQ:** F-008, F-009
- **Permiso requerido:** sesión vigente (INV-016; errores comunes 401/503 en CT-002). Toda operación por ID verifica al propietario del registro (INV-001).

Salida: `{ "id", "usuario_id", "nombre", "monto_objetivo", "monto_actual", "fecha_objetivo", "porcentaje_completado" }`

| Endpoint | Entrada | Respuesta | Errores propios |
|---|---|---|---|
| `POST /metas` | `{ "nombre": "1-100", "monto_objetivo": "> 0 y ≤ 1e12", "fecha_objetivo": "YYYY-MM-DD" }` | 200 creada (`monto_actual` = 0) | 422 |
| `GET /metas` | — | 200 lista con porcentaje | — |
| `PUT /metas/{id}` | Campos opcionales: `nombre`, `monto_objetivo` (> 0), `monto_actual` (≥ 0), `fecha_objetivo` | 200 actualizada | 404 "Meta no encontrada" |
| `DELETE /metas/{id}` | — | 200 `{ "message": "Meta eliminada" }` | 404 |
| `POST /metas/{id}/abonar` | `{ "monto": "> 0 y ≤ 1e12", "descripcion": "≤ 255 (opcional)", "fecha": "YYYY-MM-DD" }` | 200 meta actualizada | 404 "Meta no encontrada" (no se crea ningún gasto, INV-008); 500 "No se pudo registrar el abono" (se revierte el gasto; con `cuenta_id`, si falla la BD: 503 genérico y nada cambia) |

## Efectos del abono (WF-002)
1. Valida la meta (INV-008). 2. Busca o crea la categoría "Ahorro" (🐷, gasto). 3. Crea la transacción de gasto.
4. Suma el monto a `monto_actual`; si falla, elimina el gasto creado.

## Abono con cuenta (CHG-019, fase c)
`POST /metas/{id}/abonar` acepta `cuenta_id` opcional (cuenta de dinero de origen, debe ser del usuario). El gasto «Ahorro» se
crea con esa cuenta y su saldo baja dentro de la **misma transacción SQL** que suma a la meta (INV-008, INV-052). 404 «Cuenta no
encontrada» si no es suya; 409 «Saldo insuficiente…» o cuenta de dinero archivada: no se registra el gasto ni se suma a la meta; 503 si la
función SQL actualizada no está disponible (con cuenta nunca se usa el método anterior no atómico). Sin `cuenta_id` todo igual que antes.
