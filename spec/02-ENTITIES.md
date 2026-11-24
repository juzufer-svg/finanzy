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

- **Relaciones:** Usuario 1—N Categoría, Transacción, Presupuesto, Meta (borrado en cascada).
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

- **REQ:** F-004, F-005, F-010.

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

## Código de verificación (transitorio, en memoria)
- **Identidad:** propósito + correo (`correo` para verificar cuenta, `reset:correo` para restablecer).
- **Atributos:** valor (6 dígitos), vencimiento (10 min), intentos fallidos.
- **Estados:** `04-STATES.md` → Código. **Invariantes:** INV-007, INV-010.

## Contador diario (CHG-017)
- **Identidad:** (fecha, métrica, origen) — clave única. No pertenece a ningún Usuario.
- **Descripción:** consumo propio agregado por día para el Monitor; jamás guarda correos, teléfonos, textos ni ids de usuario.

| Atributo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| fecha | Fecha (día UTC) | Sí | Día en que ocurrió el consumo |
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
Contador diario: sin relación con Usuario (solo agregados)
```
