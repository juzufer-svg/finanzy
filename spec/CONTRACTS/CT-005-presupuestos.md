# CT-005 — Presupuestos `/api/v1/presupuestos`

- **Versión:** v1.1 (CHG-012: `POST /presupuestos/copiar`, nuevo) · **UC:** UC-006 · **REQ:** F-007
- **Permiso requerido:** sesión vigente (INV-016; errores comunes 401/503 en CT-002). Toda operación por ID verifica al propietario del registro (INV-001).

Salida: `{ "id", "usuario_id", "categoria_id", "limite_mensual", "mes_ano" }`

| Endpoint | Entrada | Respuesta | Errores propios |
|---|---|---|---|
| `POST /presupuestos` | `{ "categoria_id": "1-64, del usuario (INV-002)", "limite_mensual": "> 0, ≤ 9 999 999 999,99 y 2 decimales máx.", "mes_ano": "YYYY-MM" }` | 200 creado | 404 "Categoría no encontrada"; 409 «Ya hay un presupuesto para esa categoría en este mes…» (INV-028, CHG-013) |
| `POST /presupuestos/copiar` | `{ "desde": "YYYY-MM", "hacia": "YYYY-MM" }` (distintos) | 200 `{ "copiados", "omitidos", "presupuestos": [lista del mes destino] }`. Copia los del usuario en `desde` cuya categoría aún no tiene presupuesto en `hacia`; nunca reemplaza ni duplica (si una copia simultánea ya lo creó, cuenta como omitido) | 422 meses inválidos o iguales («El mes de origen y el de destino deben ser distintos») |
| `GET /presupuestos/{mes_ano}` | — | 200 lista del mes | 422 mes inválido |
| `PUT /presupuestos/{id}` | `{ "limite_mensual": "> 0, ≤ 9 999 999 999,99 y 2 decimales máx." }` | 200 actualizado | 404 "Presupuesto no encontrado" |
| `DELETE /presupuestos/{id}` | — | 200 `{ "message": "Presupuesto eliminado" }` | 404 |

Lo gastado y el porcentaje de avance se calculan en el frontend con las transacciones del mes.

**Montos (INV-003, CHG-029):** si un monto supera 9 999 999 999,99 o tiene más de 2 decimales, la respuesta es 422 con el mensaje «El monto debe tener máximo 2 decimales y no superar $9.999.999.999,99 (pesos colombianos)». En metas, el monto ahorrado admite 0 y un abono que lleve el acumulado sobre el tope responde igual y no cambia nada.
