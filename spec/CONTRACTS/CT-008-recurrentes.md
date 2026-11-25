# CT-008 — Recurrentes `/api/v1/recurrentes`

- **Versión:** v1.1 (CHG-012; CHG-019 fase c: `cuenta_id` opcional y confirmar atómico) · **UC:** UC-012 · **REQ:** F-016
- **Permiso requerido:** sesión vigente (INV-016; errores comunes 401/503 en CT-002). Toda operación por ID verifica al propietario del registro (INV-001).
- **Regla central (INV-025):** una recurrente nunca crea transacciones sola. Solo `confirmar` registra una transacción.

Salida (recurrente): `{ "id", "usuario_id", "categoria_id", "tipo", "monto", "descripcion", "medio_pago", "frecuencia", "dia_ancla", "proxima_fecha", "activa" }`

## Cuerpo de recurrente (POST y PUT)
```json
{
  "categoria_id": "texto ≤ 64 — opcional ('' = sin categoría) — debe ser del usuario (INV-002)",
  "tipo": "ingreso | gasto (INV-004)",
  "monto": "número > 0, ≤ 9 999 999 999,99 y 2 decimales máx. (INV-003)",
  "descripcion": "texto ≤ 255 — opcional",
  "medio_pago": "igual que en CT-003 — opcional (INV-022)",
  "cuenta_id": "uuid — opcional (CHG-019 fase c): cuenta de dinero del usuario; si es ajena, 404 «Cuenta no encontrada» al crear y al editar (INV-046)",
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
| `POST /recurrentes/{id}/confirmar` | `{ "ocurrencia": "YYYY-MM-DD (la próxima fecha que vio la persona)", "monto": "opcional, > 0, ≤ 9 999 999 999,99 y 2 decimales máx.", "fecha": "opcional, YYYY-MM-DD" }` | 200 `{ "transaccion": <CT-003>, "recurrente": <recurrente con la nueva próxima fecha> }` | 404; 409 «La recurrente está pausada»; 409 «Esta fecha ya se registró u omitió…» (la ocurrencia ya no es la pendiente: doble toque u otra pestaña, INV-026); 503 genérico si falla la BD (en la fase c nada cambió: la fecha sigue pendiente; ya no es 500). **Hasta la fase (c)** (flujo actual: avanza la fecha y luego crea la transacción) si además falla devolverla, 500 que avisa que la fecha quedó omitida; ese caso **desaparece en la fase (c)** (ver abajo) |
| `POST /recurrentes/{id}/omitir` | `{ "ocurrencia": "YYYY-MM-DD" }` | 200 recurrente con la nueva próxima fecha (no registra nada) | 404; 409 (igual que confirmar) |

La transacción confirmada usa la categoría, el tipo, la descripción y el medio de pago de la recurrente; el monto y
la fecha son los enviados o, si no se envían, el monto de la plantilla y la fecha de la ocurrencia.

## Próxima fecha (INV-026)
- `semanal`: + 7 días.
- `mensual`: el `dia_ancla` del mes siguiente; si el mes no lo tiene, su último día (31 → 28/29 feb → 31 mar).
- `quincenal`: dos veces al mes, en el día `a = dia_ancla` (si ≤ 15) o `dia_ancla − 15`, y en `a + 15`, ajustados al último día del mes.

## Cuenta de dinero en las recurrentes y confirmar atómico (CHG-019, fase c)
La recurrente guarda `cuenta_id` (cuenta de dinero) opcional y la salida lo incluye; al crear o editar con la cuenta de dinero de otra persona → 404 «Cuenta no encontrada» (INV-046).
`POST /recurrentes/{id}/confirmar` acepta `cuenta_id` opcional que reemplaza al de la plantilla (`null` = sin cuenta; si no se envía, se usa la de la plantilla); la
cuenta de dinero ajena → 404.

**Confirmar es UNA función SQL atómica (ADR-009 punto 13, INV-052).** El flujo **actual** (`plataapp.py` ~474-499) **avanza** la próxima fecha, luego crea la
transacción y, si falla, **intenta revertir** la fecha. Con cuentas de dinero eso es inaceptable (un saldo insuficiente haría avanzar y retroceder la fecha) y se **reemplaza**
por una sola función en la BD (patrón de `abonar_meta`, solo `service_role`) que, en una transacción: bloquea la recurrente, comprueba compare-and-set `proxima_fecha = ocurrencia`
(y que esté activa), inserta la transacción y avanza `proxima_fecha`. Si la cuenta de dinero está archivada o no tiene saldo (409, INV-048), **no se crea la transacción y
la próxima fecha no avanza** (INV-025, INV-026, INV-052). Doble toque simultáneo → una sola transacción y un 409. Sin la función SQL (migración sin aplicar) → 503, nunca el flujo anterior.
Omitir no toca ningún saldo y sigue usando solo el compare-and-set de la fecha.

**PUT y `cuenta_id` (v1.1):** no enviar = conserva, `null` = quita, valor = reemplaza; cambiar a una cuenta archivada → 409; re-enviar la misma ya guardada no bloquea (incluso pausar/activar con la cuenta archivada). Con cuenta, el monto respeta el tope y los 2 decimales de INV-051 (422), también al crear.

**Montos (INV-003, CHG-029):** si un monto supera 9 999 999 999,99 o tiene más de 2 decimales, la respuesta es 422 con el mensaje «El monto debe tener máximo 2 decimales y no superar $9.999.999.999,99 (pesos colombianos)». En metas, el monto ahorrado admite 0 y un abono que lleve el acumulado sobre el tope responde igual y no cambia nada. Con cuenta de dinero se conserva el mensaje de INV-051.
