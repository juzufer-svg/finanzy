# CT-003 — Transacciones `/api/v1/transacciones`

- **Versión:** v1.1 (CHG-007: `medio_pago`, campo nuevo y opcional; compatible con clientes anteriores) · **UC:** UC-004, UC-008 · **REQ:** F-004, F-005, F-010
- **Permiso requerido:** sesión vigente (INV-016; errores comunes 401/503 en CT-002). Toda operación por ID verifica al propietario del registro (INV-001).

Errores comunes: 401 "Token inválido" · 404 "Transacción no encontrada" (no existe o es de otro usuario) · 422 validación.

## Cuerpo de transacción (POST y PUT)
```json
{
  "categoria_id": "texto ≤ 64 — opcional ('' = sin categoría) — debe ser del usuario (INV-002)",
  "monto": "número > 0 y ≤ 1e12 (INV-003)",
  "descripcion": "texto ≤ 255 — opcional",
  "fecha": "YYYY-MM-DD (INV-005)",
  "tipo": "ingreso | gasto (INV-004)",
  "medio_pago": "debito | credito | efectivo | transferencia | nequi_daviplata | null — opcional (INV-022)"
}
```
Salida: `{ "id", "usuario_id", "categoria_id", "monto", "descripcion", "fecha", "tipo", "medio_pago" }`
(`medio_pago` es `null` en transacciones sin medio: las anteriores a CHG-007 y los abonos a metas).

`medio_pago` en `PUT`: si no se envía, se conserva el actual; `null` lo quita; otro valor lo reemplaza.
Un valor fuera de la lista → 422.

| Endpoint | Respuesta | Errores propios |
|---|---|---|
| `POST /transacciones` | 200 transacción creada | 404 "Categoría no encontrada" si la categoría no es del usuario |
| `GET /transacciones?mes=YYYY-MM` | 200 lista (más recientes primero); sin `mes` = todas | 422 "Formato de mes inválido (YYYY-MM)" |
| `GET /transacciones/resumen/{mes}` | 200 `{ "ingresos", "gastos", "balance", "total_transacciones" }` | 422 mes inválido |
| `GET /transacciones/{id}` | 200 transacción | 404 |
| `PUT /transacciones/{id}` | 200 transacción actualizada | 404 (transacción o categoría ajena) |
| `DELETE /transacciones/{id}` | 200 `{ "message": "Transacción eliminada" }` | 404 |
