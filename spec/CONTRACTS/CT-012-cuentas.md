# CT-012 — Cuentas de dinero y transferencias `/api/v1/cuentas` y `/api/v1/transferencias`

- **Versión:** v1 (CHG-019, ciclo 2) · **UC:** UC-016 · **REQ:** F-020 · **ADR:** ADR-009 · **INV:** INV-046 a INV-052 (y INV-001, INV-021)
- **Vocabulario:** en este contrato «cuenta de dinero» es la entidad `cuentas`; «cuenta» sola es la cuenta de usuario. Una cuenta de dinero está **archivada** o **no archivada**. «Transacción» es un ingreso o gasto; «movimientos» es el conjunto de transacciones y transferencias.
- **Permiso requerido:** sesión vigente (INV-016; errores comunes 401/503 en CT-002). Toda operación por ID verifica al propietario del registro (INV-001, INV-046): una cuenta de dinero o transferencia inexistente o de otro usuario responde **404** igual.
- **Fases:** `/cuentas` y `cuenta_id` en transacciones = fase (a); `/transferencias` = fase (b); `cuenta_id` en abonos, recurrentes y WhatsApp, y la columna Cuenta de CT-011 = fase (c).
- Todos los montos van y vuelven en **COP** (la moneda de visualización se aplica solo en la interfaz, REQ-F-011).

## Cuenta de dinero (salida)
```json
{
  "id": "uuid", "usuario_id": "uuid",
  "nombre": "texto 1-100",
  "tipo": "efectivo | ahorros_corriente | billetera_digital | tarjeta_credito",
  "saldo_inicial": 150000.00,
  "saldo": 98500.50,
  "archivada": false,
  "created_at": "2026-11-24T15:00:00Z"
}
```
`saldo` lo **calcula** el servidor en cada consulta (INV-047): `saldo_inicial + ingresos − gastos + transferencias recibidas − enviadas`, incluyendo **todas** las transacciones y transferencias registradas con esa cuenta de dinero aunque su fecha sea futura (decisión del dueño); nunca se envía ni se guarda. Negativo = deuda (solo en `tarjeta_credito`).

## Cuentas de dinero (fase a)
Los montos de entrada se leen con `Decimal` (INV-051): un número con más de 2 decimales (`12.345`, `0.001`) es 422.

| Endpoint | Entrada | Respuesta | Errores propios |
|---|---|---|---|
| `POST /cuentas` | `{ "nombre": "1-100", "tipo": "…", "saldo_inicial": "número con ≤ 2 decimales, 0 ≤ x ≤ 9 999 999 999,99 (tarjeta_credito: también negativo hasta −9 999 999 999,99)" }` | 200 cuenta de dinero creada | 409 «Ya tienes una cuenta con ese nombre»; 409 «Llegaste al máximo de 20 cuentas» (INV-050); 422 (tipo, montos, decimales: INV-051) |
| `GET /cuentas?incluir_archivadas=true\|false` | por defecto `false` (solo las no archivadas) | 200 lista (por nombre) con `saldo` | — |
| `GET /cuentas/{id}` | — | 200 cuenta de dinero | 404 «Cuenta no encontrada» |
| `PUT /cuentas/{id}` | opcionales: `nombre`, `saldo_inicial`, `archivada`. El `tipo` **no** se puede cambiar | 200 cuenta de dinero | 404; 409 nombre repetido; 409 saldo insuficiente si el nuevo `saldo_inicial` deja una cuenta de dinero que no es tarjeta en negativo (INV-048); 422 |
| `DELETE /cuentas/{id}` | — | 200 `{ "message": "Cuenta eliminada" }` solo si no tiene transacciones ni transferencias | 404; 409 «Esta cuenta tiene movimientos. Archívala en lugar de eliminarla» (INV-050) |

## Transferencias (fase b)
Salida: `{ "id", "usuario_id", "cuenta_origen_id", "cuenta_destino_id", "monto", "fecha", "descripcion", "created_at" }`

| Endpoint | Entrada | Respuesta | Errores propios |
|---|---|---|---|
| `POST /transferencias` | `{ "cuenta_origen_id", "cuenta_destino_id", "monto": "> 0 y ≤ 9 999 999 999,99, ≤ 2 decimales", "fecha": "YYYY-MM-DD", "descripcion": "≤ 255 (opcional)" }` | 200 transferencia creada; los dos saldos se mueven juntos (INV-049) | 404 «Cuenta no encontrada» (cualquiera de las dos no es suya, sin decir cuál); 422 «Elige dos cuentas distintas»; 409 «La cuenta … está archivada»; 409 saldo insuficiente en el origen (INV-048); 422 montos |
| `GET /transferencias?mes=YYYY-MM` | `mes` opcional (sin él, todas) | 200 lista (más recientes primero) | 422 «Formato de mes inválido (YYYY-MM)» |
| `DELETE /transferencias/{id}` | — | 200 `{ "message": "Transferencia eliminada" }` | 404 «Transferencia no encontrada»; 409 si dejaría la cuenta de dinero destino (que no es tarjeta) en negativo; 409 si una de las dos cuentas de dinero está archivada |

No hay `PUT`: se elimina y se crea otra. Sin comisión. Una transferencia **no** es ingreso ni gasto (INV-049): no aparece en `GET /transacciones`, ni en `resumen/{mes}`, presupuestos, reportes, asistente ni exportación; la interfaz la muestra en la lista de movimientos con los datos de `GET /transferencias`.

## Errores de saldo y de cuenta de dinero archivada
Los errores de la regla de saldo vienen de la BD (SQLSTATE `FZ001` saldo negativo, `FZ002` cuenta de dinero archivada, `FZ003` tope de cuentas de dinero; los dos primeros se evalúan en un disparador `BEFORE` bajo el mismo bloqueo de las cuentas de dinero implicadas, ADR-009 punto 5) y el backend los traduce siempre a **409** con `detail` legible, por ejemplo:
- «Saldo insuficiente: esto dejaría la cuenta «Efectivo» en negativo. Solo las tarjetas de crédito pueden quedar en negativo.»
- «La cuenta «Ahorros» está archivada. Desarchívala para registrar movimientos.»
Nunca se devuelve 500 ni el mensaje crudo de la BD, y un interbloqueo de la BD (`40P01`) no debería ocurrir (se prueba que son 0). La operación rechazada no guarda nada (INV-048).

## Cambios aditivos en otros contratos (la compatibilidad se mantiene: el campo es opcional)
- **CT-003 v1.2 (fase a):** `cuenta_id` en `POST/PUT /transacciones` y en la salida: «uuid ≤ 64 — opcional; `null`/ausente = sin cuenta; debe ser una cuenta de dinero del usuario». En `PUT`: no enviar = conservar, `null` = quitar, valor = reemplazar; un `PUT` que solo cambia `cuenta_id` valida el monto ya guardado (INV-051). 404 «Cuenta no encontrada» (no es suya); 409 por saldo o por cuenta de dinero archivada. Las transacciones anteriores salen con `cuenta_id: null` y no mueven ningún saldo.
- **CT-006 v1.1 (fase c):** `POST /metas/{id}/abonar` acepta `cuenta_id` opcional (cuenta de dinero de origen). 404 si no es suya; 409 saldo insuficiente → no se registra el gasto ni se suma a la meta (INV-008); sin la función SQL nueva y con `cuenta_id` → 503.
- **CT-008 v1.1 (fase c):** `cuenta_id` opcional en la recurrente y en `confirmar` (reemplaza la de la plantilla). Confirmar es una función SQL atómica: si falla por cuenta de dinero archivada o saldo (409), **no avanza** la fecha (INV-026, INV-052).
- **CT-009 v1.1 (fase c):** la IA de WhatsApp puede devolver `cuenta` (nombre) **solo si el usuario la nombró**; el backend la busca entre las cuentas de dinero no archivadas del usuario (sin distinguir mayúsculas ni tildes). No existe → no registra y responde «No encontré la cuenta «X»; escribe el nombre exacto o registra sin cuenta». Saldo insuficiente → no registra y lo explica. A Claude se le envían solo los **nombres** de las cuentas de dinero no archivadas (sin ids ni saldos) (INV-029). WhatsApp no crea transferencias.
- **CT-007 v1.1 (fase c):** nueva herramienta de **solo lectura** `cuentas_y_saldos` (INV-023).
- **CT-011 v1.1 (fase c):** columna 8 «Cuenta» al final del archivo.

## Compatibilidad
Los campos nuevos son opcionales y aditivos. Cambiar el significado de `saldo`, permitir otro tipo editable o quitar `409` exige nueva versión y ADR.
