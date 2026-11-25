# CT-003 — Transacciones `/api/v1/transacciones`

- **Versión:** v1.2 (CHG-007: `medio_pago`; CHG-019 fase a: `cuenta_id`, campo nuevo y opcional; compatibles con clientes anteriores) · **UC:** UC-004, UC-008 · **REQ:** F-004, F-005, F-010
- **Permiso requerido:** sesión vigente (INV-016; errores comunes 401/503 en CT-002). Toda operación por ID verifica al propietario del registro (INV-001).

Errores comunes: 401 "Token inválido" · 404 "Transacción no encontrada" (no existe o es de otro usuario) · 422 validación.

## Cuerpo de transacción (POST y PUT)
```json
{
  "categoria_id": "texto ≤ 64 — opcional ('' = sin categoría) — debe ser del usuario (INV-002)",
  "monto": "número > 0 y ≤ 1e12 (INV-003)",
  "descripcion": "texto ≤ 255 — opcional",
  "fecha": "YYYY-MM-DD (INV-005), entre 2026-01-01 y hoy + 365 días (día de Colombia) (INV-063)",
  "tipo": "ingreso | gasto (INV-004)",
  "medio_pago": "debito | credito | efectivo | transferencia | nequi_daviplata | null — opcional (INV-022)",
  "cuenta_id": "uuid ≤ 64 — opcional (CHG-019, fase a): null/ausente = sin cuenta; debe ser una cuenta de dinero del usuario (INV-046) y no estar archivada; monto ≤ 9 999 999 999,99 y ≤ 2 decimales con cuenta de dinero (INV-051)"
}
```
Salida: `{ "id", "usuario_id", "categoria_id", "monto", "descripcion", "fecha", "tipo", "medio_pago", "cuenta_id" }`
(`medio_pago` es `null` en transacciones sin medio: las anteriores a CHG-007 y los abonos a metas).

`medio_pago` en `PUT`: si no se envía, se conserva el actual; `null` lo quita; otro valor lo reemplaza.
Un valor fuera de la lista → 422.

`cuenta_id` (CHG-019, cuenta de dinero): las transacciones anteriores salen con `null` y **no mueven ningún saldo**. En `PUT`, igual que `medio_pago`:
no enviar = conservar; `null` = quitar; otro valor = reemplazar. Un `PUT` que solo cambia `cuenta_id` valida el monto ya guardado
(≤ 9 999 999 999,99 y 2 decimales, leído con `Decimal`): si no cumple, 422 (INV-051). Errores propios: **404** «Cuenta no encontrada» (no es suya o no
existe, INV-046); **409** «Saldo insuficiente…» si la transacción dejaría una cuenta de dinero que no es tarjeta de crédito en negativo, o
«La cuenta … está archivada…» (INV-048, INV-050); en ambos casos no se guarda nada. Ver CT-012. Las transferencias entre cuentas de dinero
**no** son transacciones: no salen en `GET /transacciones` ni en `resumen/{mes}` (INV-049).

| Endpoint | Respuesta | Errores propios |
|---|---|---|
| `POST /transacciones` | 200 transacción creada | 404 "Categoría no encontrada" si la categoría no es del usuario; 422 «La fecha debe estar entre el 1 de enero de 2026 y el dd/mm/aaaa» si la fecha está fuera de rango (INV-063, CHG-027) |
| `GET /transacciones?mes=YYYY-MM` | 200 lista (más recientes primero); sin `mes` = todas | 422 "Formato de mes inválido (YYYY-MM)" |
| `GET /transacciones/resumen/{mes}` | 200 `{ "ingresos", "gastos", "balance", "total_transacciones" }` | 422 mes inválido |
| `GET /transacciones/{id}` | 200 transacción | 404 |
| `PUT /transacciones/{id}` | 200 transacción actualizada | 404 (transacción o categoría ajena); 422 igual que en `POST` **solo si la fecha cambia** respecto a la guardada (una edición que no la cambia no se rechaza por el rango) (INV-063) |
| `DELETE /transacciones/{id}` | 200 `{ "message": "Transacción eliminada" }` | 404 |
