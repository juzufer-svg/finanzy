# Glosario (vocabulario controlado)

Usar **solo** estos términos en spec, interfaz y pruebas. En el código se aceptan los nombres técnicos indicados.

| Término oficial | Definición | En código | Términos a evitar | Ejemplo |
|---|---|---|---|---|
| Usuario | Persona con cuenta en Finanzy | `users`, `usuario_id` | cliente, miembro | — |
| Cuenta pendiente | Usuario registrado que aún no verificó su correo | `is_active = false` | cuenta inactiva, no confirmada | Se elimina tras 1 hora |
| Cuenta activa | Usuario que verificó su correo | `is_active = true` | — | Puede iniciar sesión |
| Sesión | Token JWT que identifica al usuario durante 7 días | `access_token` | login, cookie | — |
| Código | Número de 6 dígitos enviado por correo para verificar la cuenta o restablecer la contraseña | `code` | OTP, PIN, token | `482913` |
| Transacción | Ingreso o gasto del usuario | `transacciones` | operación, registro (y «movimiento» para una sola transacción: ver Movimiento) | Gasto de 42.50 en Comida |
| Ingreso | Transacción que suma dinero | `tipo = "ingreso"` | entrada, abono (salvo metas) | Salario |
| Gasto | Transacción que resta dinero | `tipo = "gasto"` | egreso, salida, débito | Supermercado |
| Categoría | Agrupación de transacciones de un tipo, propia de cada usuario | `categorias` | rubro, etiqueta | 🍔 Comida |
| Presupuesto | Límite mensual de gasto para una categoría | `presupuestos` | tope, límite (como sustantivo de entidad) | Comida: 500 000 en 2026-11 |
| Meta | Objetivo de ahorro con monto y fecha | `metas` | objetivo, alcancía | Viaje: 3 000 000 para 2027-06 |
| Abono | Aporte de dinero a una meta; genera un gasto en "Ahorro" | `abonar` | depósito, aporte | — |
| Mes | Periodo de consulta en formato `YYYY-MM` | `mes`, `mes_ano` | periodo | `2026-11` |
| Resumen | Totales del mes: ingresos, gastos, balance, cantidad | `resumen` | estado de cuenta | — |
| Balance | Ingresos − gastos del mes (no depende de las cuentas de dinero) | `balance` | saldo (reservado para una cuenta de dinero, CHG-019) | — |
| Dueño | **Actor** (CHG-017): el Usuario cuya sesión verificada tiene el correo de `OWNER_EMAIL`; su único privilegio extra es ver el Monitor. Es distinto del «propietario del registro» (INV-001) | `OWNER_EMAIL` | administrador, admin, superusuario; usar «propietario del registro» para el dueño de un dato | — |
| Monitor | Página y ruta de solo lectura (`/monitor/resumen`) que muestra al Dueño los consumos de las plataformas y los contadores propios | `monitor` | panel de administración, diagnóstico | — |
| Contador diario | Cantidad agregada por día UTC, métrica y origen de un consumo propio (llamadas y tokens de Claude, correos enviados, mensajes de WhatsApp); sin datos personales | `contadores` | estadística, log de uso | Claude, origen `asistente`, 2026-11-24: 4 llamadas |
| Plataforma | Servicio externo cuyo consumo lee el Monitor: Railway, Anthropic, Meta, Supabase, Vercel o Brevo | `plataformas` | proveedor, servicio (como término oficial) | — |
| Cuenta de dinero | (CHG-019) Lugar donde la persona tiene dinero, creado a mano: efectivo, ahorros/corriente, billetera digital o tarjeta de crédito. **No** es la cuenta de usuario ni una cuenta bancaria conectada. La interfaz puede mostrar «Cuenta» en el menú; en la spec, «cuenta» sola sigue siendo la cuenta de usuario | `cuentas`, `cuenta_id` | cuenta bancaria (como término), billetera, wallet | Efectivo, Ahorros Bancolombia, Tarjeta Visa |
| Movimiento | (CHG-019) Palabra de la interfaz y de la spec para el conjunto de transacciones y transferencias entre cuentas que ve la persona en su lista; «Movimientos anteriores» = transacciones sin cuenta | — | operación | La lista de movimientos del mes |
| Saldo | (CHG-019) Dinero actual de una cuenta de dinero: saldo inicial + ingresos − gastos ± transferencias de sus movimientos; derivado, en COP, nunca guardado. No confundir con el Balance (ingresos − gastos del mes) | `saldo` | balance (para una cuenta), disponible | 98 500,50 |
| Saldo inicial | (CHG-019) Dinero que la persona dice tener en la cuenta al crearla; los movimientos anteriores no se cuentan | `saldo_inicial` | apertura, base | 150 000 |
| Archivar | (CHG-019) Congelar una cuenta de dinero con movimientos: no admite movimientos nuevos ni cambios, y no se elimina | `archivada` | desactivar, cerrar | — |
| Sin cuenta | (CHG-019) Transacción sin cuenta de dinero (todas las anteriores a CHG-019); no mueve ningún saldo | `cuenta_id` NULL | huérfana | — |
| Transferencia entre cuentas | (CHG-019) Movimiento de dinero entre dos cuentas de dinero propias; **no** es ingreso ni gasto. No confundir con el medio de pago «Transferencia» (cómo se pagó) | `transferencias` | traspaso, movimiento interno | Efectivo → Ahorros: 40 000 |
| Exportación | (CHG-018) Archivo CSV o Excel (.xlsx) con las transacciones de un mes o rango de hasta 12 meses, montos en COP | `exportaciones` | reporte, backup, respaldo | `finanzy-transacciones-2026-11.csv` |
| Estado de autenticación | (CHG-020) Bloqueos de login, códigos de verificación/restablecimiento y ventanas de límites de envío/intentos; persistidos en PostgreSQL con huellas HMAC | `auth_*` | caché de seguridad, sesión | — |
| Huella | (CHG-020) HMAC-SHA256 con clave derivada de `SECRET_KEY` del correo o la IP; es lo único que se guarda de ellos en el estado de autenticación | `clave` | hash del correo, ID de IP | — |
| Moneda de visualización | Moneda en que se muestran los montos (se guardan en COP) | `currency` | divisa | USD |
