# Entidades del dominio

> Modelo del negocio. Persistencia: tablas de Supabase descritas en `PLATAAPP_SCHEMA.sql`.

## Usuario
- **Identidad:** `id` (UUID). El correo también es único.
- **Descripción:** persona dueña de todos sus datos financieros.

| Atributo | Tipo (conceptual) | Obligatorio | Regla / Value Object |
|---|---|---|---|
| correo | Email | Sí | Único, guardado en minúsculas (INV-014) |
| contraseña | Hash bcrypt | Sí | Nunca se guarda en claro (VO Contraseña) |
| nombre completo | Texto | Sí (registro) | 2-100 caracteres |
| moneda | Código de moneda | Sí | USD, EUR, MXN, ARS, COP, CLP |
| activa | Booleano | Sí | Ver estados |

- **Relaciones:** Usuario 1—N Categoría, Transacción, Presupuesto, Meta, Cuenta de dinero, Transferencia (borrado en cascada). «Cuenta» sola significa la cuenta de usuario; la entidad nueva siempre se llama «cuenta de dinero» (glosario).
- **Estados:** `04-STATES.md` → Usuario. **Invariantes:** INV-006, INV-014, INV-015. **REQ:** F-001, F-002, F-003, F-013, F-014.

## Categoría
- **Identidad:** `id` (UUID).

| Atributo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| usuario | Usuario | Sí | Propietario del registro (INV-001) |
| nombre | Texto | Sí | 1-100 caracteres |
| ícono | Emoji | No | ≤ 16 caracteres |
| tipo | Tipo de transacción | Sí | INV-004 |

- **Reglas:** el usuario recibe 7 categorías por defecto al primer acceso. "Ahorro" se crea automáticamente con el primer abono.
- **REQ:** F-006.

## Transacción
- **Identidad:** `id` (UUID).

| Atributo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| usuario | Usuario | Sí | Propietario del registro (INV-001) |
| categoría | Categoría | No | Si se indica, debe ser del usuario (INV-002). Si la categoría se borra, queda sin categoría |
| monto | Monto | Sí | INV-003 |
| tipo | Tipo de transacción | Sí | INV-004 |
| fecha | Fecha | Sí | INV-005 |
| descripción | Texto | No | ≤ 255 caracteres |
| cuenta de dinero (CHG-019) | Cuenta de dinero | No | `cuenta_id`; NULL = sin cuenta (las transacciones anteriores a CHG-019). Si se indica, es del usuario y no está archivada (INV-046, INV-050); mueve el saldo de esa cuenta de dinero (INV-047, INV-048); con cuenta de dinero, monto ≤ 9 999 999 999,99 y 2 decimales (INV-051) |

- **Nota:** el medio de pago (CHG-007) y la cuenta de dinero son independientes: uno dice cómo se pagó, la otra dónde está el dinero. Una transacción con fecha futura ya cuenta en el saldo de su cuenta de dinero (decisión del dueño).
- **REQ:** F-004, F-005, F-010, F-020.

## Presupuesto
- **Identidad:** `id` (UUID).

| Atributo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| usuario | Usuario | Sí | Propietario del registro (INV-001) |
| categoría | Categoría | Sí | Del usuario (INV-002); si se borra la categoría, se borra el presupuesto |
| límite mensual | Monto | Sí | INV-003 |
| mes | Mes | Sí | INV-005 |

- **Derivado:** gastado = suma de gastos del mes en esa categoría; avance = gastado / límite.
- **REQ:** F-007.

## Meta
- **Identidad:** `id` (UUID).

| Atributo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| usuario | Usuario | Sí | Propietario del registro (INV-001) |
| nombre | Texto | Sí | 1-100 caracteres |
| monto objetivo | Monto | Sí | INV-003 |
| monto ahorrado | Monto | Sí | ≥ 0, inicia en 0 (INV-003) |
| fecha objetivo | Fecha | Sí | INV-005 |

- **Derivado:** porcentaje completado = ahorrado / objetivo × 100; completada si ahorrado ≥ objetivo.
- **Estados:** `04-STATES.md` → Meta. **Invariantes:** INV-008. **REQ:** F-008, F-009.

## Código de verificación (persistido en PostgreSQL desde CHG-020)
- **Identidad:** (huella del correo, propósito) — `verify` para verificar la cuenta, `reset` para restablecer la contraseña; uno vigente por correo y propósito.
- **Atributos:** huella HMAC del código (nunca el valor en claro, INV-040), emisión y vencimiento (10 min), intentos fallidos (máx. 5).
- **Reglas:** RLS sin políticas, solo `service_role`; emisión (60 s + topes + guardado) en una sola función atómica y verificación y consumo atómicos (INV-038); para correos inexistentes o ya activos se guarda un **código señuelo** que nunca se envía ni puede verificarse (INV-009, INV-039); se purga a los 30 días y se borra con la cuenta de usuario (INV-040). Sin Supabase y fuera de producción, en memoria (INV-041).
- **Estados:** `04-STATES.md` → Código. **Invariantes:** INV-007, INV-010, INV-037 a INV-041. **REQ:** F-001, F-003.

## Intento de login (CHG-020)
- **Identidad:** huella HMAC del correo. No pertenece a un Usuario por llave foránea (existe también para correos inexistentes, INV-009).
- **Atributos:** fallos (0-5; incluye los intentos reservados que aún se están comprobando), `en_vuelo` (reservas todavía sin resolver), inicio de la ventana de **24 h** desde el primer fallo de la serie, bloqueado hasta (15 min desde el 5.º). **Estados:** `04-STATES.md` → Bloqueo de login.
- **Reglas:** el intento se reserva antes de comprobar la contraseña y la reserva se resuelve después (INV-038); todas las horas son las de la BD (`now()`); RLS sin políticas; purga a 30 días; se borra al eliminar la cuenta. **Invariantes:** INV-010, INV-037 a INV-041. **REQ:** F-002, F-014 (CA-3).

## Evento de límite (CHG-020)
- **Identidad:** id; clave = huella HMAC de `tipo:valor` (IP, correo destinatario o `global`) y hora del evento.
- **Descripción:** una fila por correo enviado, pedido de código o intento de credenciales/códigos, para las ventanas deslizantes de INV-010 (10/día por destinatario, 250/día total, 10/hora por IP, 30/10 min por IP). Sin correos ni IP en claro. **Retención 2 días** (las ventanas útiles son ≤ 24 h) y tope de 500 000 filas (una IP falsificada en `X-Forwarded-For` crea una clave nueva por petición; el crecimiento queda acotado, INV-040); no se borra con la cuenta (por eso la baja deja huellas de límites hasta 2 días) y la marca de «última purga» es una fila con clave `purga` en esta misma tabla. **REQ:** N-002.

## Cuenta de dinero (CHG-019)
- **Identidad:** `id` (UUID); nombre único por usuario (sin distinguir mayúsculas ni espacios). Se llama siempre «cuenta de dinero» (la «cuenta» sola es la de usuario).

| Atributo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| usuario | Usuario | Sí | Propietario del registro (INV-001, INV-046) |
| nombre | Texto | Sí | 1-100 caracteres; único por usuario (INV-050) |
| tipo | Enumeración | Sí | `efectivo`, `ahorros_corriente`, `billetera_digital`, `tarjeta_credito`; no editable |
| saldo inicial | Monto | Sí | 2 decimales, ≤ 9 999 999 999,99; negativo solo en `tarjeta_credito` (INV-051) |
| archivada | Booleano | Sí | Una cuenta de dinero archivada está congelada (INV-050); la contraria es «no archivada» |

- **Derivado (no persistido):** saldo = saldo inicial + ingresos − gastos + transferencias recibidas − enviadas, en COP, de todas las transacciones y transferencias con esa cuenta de dinero, aunque su fecha sea futura (INV-047). Solo la tarjeta de crédito puede quedar en negativo (INV-048). Máximo 20 por usuario. Una cuenta de dinero con transacciones o transferencias no se elimina, se archiva.
- **Relaciones:** Cuenta de dinero 1—N Transacción (opcional, `cuenta_id`), 1—N Recurrente (opcional, fase c), 1—N Transferencia (como origen y como destino).
- **Estados:** `04-STATES.md` → Cuenta de dinero. **Invariantes:** INV-046 a INV-052, INV-021. **REQ:** F-020. Es una cuenta **manual**: no hay conexión con bancos.

## Transferencia entre cuentas (CHG-019)
- **Identidad:** `id` (UUID).

| Atributo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| usuario | Usuario | Sí | Propietario del registro (INV-001) |
| cuenta de dinero origen / destino | Cuenta de dinero | Sí | Del usuario, distintas y no archivadas (INV-046, INV-049, INV-050) |
| monto | Monto | Sí | > 0, ≤ 9 999 999 999,99, 2 decimales (INV-051) |
| fecha | Fecha | Sí | INV-005 |
| descripción | Texto | No | ≤ 255 caracteres |

- **Reglas:** sin comisión; **no es ingreso ni gasto** (no está en `transacciones`: no cuenta en resumen, presupuestos, reportes, asistente ni exportación); mueve los saldos de las dos cuentas de dinero a la vez o ninguno; se crea y se elimina, no se edita (INV-049). **REQ:** F-020.

## Contador diario (CHG-017)
- **Identidad:** (fecha, métrica, origen) — clave única. No pertenece a ningún Usuario.
- **Descripción:** consumo propio agregado por día para el Monitor; jamás guarda correos, teléfonos, textos ni ids de usuario.

| Atributo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| fecha | Fecha (día de Colombia, UTC−5) | Sí | Día en que ocurrió el consumo |
| métrica | Texto de lista fija | Sí | Solo estos nombres (CT-010): `claude_llamadas`, `claude_tokens_entrada`, `claude_tokens_salida`, `brevo_correos_enviados`, `whatsapp_enviados`, `whatsapp_recibidos`, y `purga` (fila marcadora, no es consumo) |
| origen | Texto de lista fija | Sí | `asistente` o `whatsapp` para Claude; `general` cuando no aplica |
| cantidad | Entero | Sí | ≥ 0; se incrementa de forma atómica (varias escrituras simultáneas no pierden cuenta) |

- **Reglas:** RLS activado (solo `service_role`); retención 90 días (se borran filas con fecha < hoy − 90) con purga oportunista al escribir, como mucho una vez al día, con la marca de «última purga» en la propia tabla (fila `purga`/`general` del día) para soportar varias instancias; un fallo al escribirlo nunca rompe el flujo principal. **Estados:** ninguno (`04-STATES.md`). **Invariantes:** INV-036. **REQ:** F-018.

## Mapa de relaciones
```
Usuario 1—N Categoría 1—N Transacción
Usuario 1—N Transacción
Usuario 1—N Presupuesto N—1 Categoría
Usuario 1—N Meta  (un Abono crea 1 Transacción de gasto en la Categoría "Ahorro")
Usuario 1—N Cuenta de dinero 1—N Transacción (opcional)
Usuario 1—N Transferencia N—1 Cuenta de dinero (origen) y N—1 Cuenta de dinero (destino)
Intento de login, Código y Evento de límite: claves por huella HMAC, sin llave foránea a Usuario (INV-040)
Contador diario: sin relación con Usuario (solo agregados)
```
