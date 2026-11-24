# CT-008 — Recurrentes `/api/v1/recurrentes`

- **Versión:** v1 (CHG-012) · **UC:** UC-012 · **REQ:** F-016
- **Permiso requerido:** sesión vigente (INV-016; errores comunes 401/503 en CT-002). Toda operación por ID verifica al propietario del registro (INV-001).
- **Regla central (INV-025):** una recurrente nunca crea transacciones sola. Solo `confirmar` registra una transacción.

Salida (recurrente): `{ "id", "usuario_id", "categoria_id", "tipo", "monto", "descripcion", "medio_pago", "frecuencia", "dia_ancla", "proxima_fecha", "activa" }`

## Cuerpo de recurrente (POST y PUT)
```json
{
  "categoria_id": "texto ≤ 64 — opcional ('' = sin categoría) — debe ser del usuario (INV-002)",
  "tipo": "ingreso | gasto (INV-004)",
  "monto": "número > 0 y ≤ 1e12 (INV-003)",
  "descripcion": "texto ≤ 255 — opcional",
  "medio_pago": "igual que en CT-003 — opcional (INV-022)",
  "frecuencia": "mensual | quincenal | semanal",
  "proxima_fecha": "YYYY-MM-DD exacta (primera fecha al crear; próxima al editar). Una fecha inexistente → 422 «Fecha inválida (YYYY-MM-DD)»",
  "activa": "booleano — opcional (por defecto true)"
}
```
`dia_ancla` lo calcula el servidor: al crear, el día de `proxima_fecha`; al editar, solo cambia si cambió `proxima_fecha`.

| Endpoint | Entrada | Respuesta | Errores propios |
|---|---|---|---|
| `GET /recurrentes` | — | 200 lista (por próxima fecha) | — |
| `GET /recurrentes/pendientes?hasta=YYYY-MM-DD` | `hasta` opcional (el frontend envía su fecha local; por defecto, hoy en UTC) | 200 las **activas** con `proxima_fecha ≤ hasta` | 422 fecha inválida |
| `POST /recurrentes` | Cuerpo | 200 creada (no registra ninguna transacción) | 404 «Categoría no encontrada»; 422 |
| `PUT /recurrentes/{id}` | Cuerpo; `proxima_fecha` **opcional** (sin ella la fecha no cambia: pausar, editar el monto) y, si se cambia, `proxima_fecha_vista` = la fecha actual que vio la persona | 200 actualizada | 404 «Recurrente no encontrada» / «Categoría no encontrada»; 409 «La próxima fecha cambió mientras editabas…» si `proxima_fecha_vista` no es la vigente (INV-026) |
| `DELETE /recurrentes/{id}` | — | 200 `{ "message": "Recurrente eliminada" }` (las transacciones ya registradas se conservan) | 404 |
| `POST /recurrentes/{id}/confirmar` | `{ "ocurrencia": "YYYY-MM-DD (la próxima fecha que vio la persona)", "monto": "opcional, > 0 y ≤ 1e12", "fecha": "opcional, YYYY-MM-DD" }` | 200 `{ "transaccion": <CT-003>, "recurrente": <recurrente con la nueva próxima fecha> }` | 404; 409 «La recurrente está pausada»; 409 «Esta fecha ya se registró u omitió…» (la ocurrencia ya no es la pendiente: doble toque u otra pestaña, INV-026); 500 «No se pudo registrar la transacción» (la ocurrencia vuelve a quedar pendiente); si además falla devolverla, 500 que avisa que la fecha quedó omitida y debe registrarse a mano |
| `POST /recurrentes/{id}/omitir` | `{ "ocurrencia": "YYYY-MM-DD" }` | 200 recurrente con la nueva próxima fecha (no registra nada) | 404; 409 (igual que confirmar) |

La transacción confirmada usa la categoría, el tipo, la descripción y el medio de pago de la recurrente; el monto y
la fecha son los enviados o, si no se envían, el monto de la plantilla y la fecha de la ocurrencia.

## Próxima fecha (INV-026)
- `semanal`: + 7 días.
- `mensual`: el `dia_ancla` del mes siguiente; si el mes no lo tiene, su último día (31 → 28/29 feb → 31 mar).
- `quincenal`: dos veces al mes, en el día `a = dia_ancla` (si ≤ 15) o `dia_ancla − 15`, y en `a + 15`, ajustados al último día del mes.
