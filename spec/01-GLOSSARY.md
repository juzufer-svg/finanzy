# Glosario (vocabulario controlado)

Usar **solo** estos términos en spec, interfaz y pruebas. En el código se aceptan los nombres técnicos indicados.

| Término oficial | Definición | En código | Términos a evitar | Ejemplo |
|---|---|---|---|---|
| Usuario | Persona con cuenta en Finanzy | `users`, `usuario_id` | cliente, miembro | — |
| Cuenta (sola) | La cuenta **de usuario** de la persona en Finanzy (correo y contraseña). Cuando se habla de la entidad nueva de CHG-019 se dice siempre «cuenta de dinero» | `users` | usar «cuenta» a secas para una cuenta de dinero | Eliminar la cuenta |
| Cuenta pendiente | Cuenta (de usuario) cuyo correo aún no se verificó | `is_active = false` | cuenta inactiva, no confirmada | Se elimina tras 1 hora |
| Cuenta activa | Cuenta (de usuario) cuyo correo se verificó. **Solo** se usa para cuentas de usuario; una cuenta de dinero está «archivada» o «no archivada» | `is_active = true` | — | Puede iniciar sesión |
| Sesión | Token JWT que identifica al usuario durante 7 días | `access_token` | login, cookie | — |
| Código | Número de 6 dígitos enviado por correo para verificar la cuenta o restablecer la contraseña | `code` | OTP, PIN, token | `482913` |
| Transacción | **Un** ingreso o gasto del usuario (el registro individual) | `transacciones` | operación, registro, y «movimiento» para una sola transacción (ver Movimiento) | Gasto de 42.50 en Comida |
| Ingreso | Transacción que suma dinero | `tipo = "ingreso"` | entrada, abono (salvo metas) | Salario |
| Gasto | Transacción que resta dinero | `tipo = "gasto"` | egreso, salida, débito | Supermercado |
| Categoría | Agrupación de transacciones de un tipo, propia de cada usuario | `categorias` | rubro, etiqueta | 🍔 Comida |
| Presupuesto | Límite mensual de gasto para una categoría | `presupuestos` | tope, límite (como sustantivo de entidad) | Comida: 500 000 en 2026-11 |
| Meta | Objetivo de ahorro con monto y fecha | `metas` | objetivo, alcancía | Viaje: 3 000 000 para 2027-06 |
| Abono | Aporte de dinero a una meta; genera un gasto en "Ahorro" | `abonar` | depósito, aporte | — |
| Mes | Periodo de consulta en formato `YYYY-MM` | `mes`, `mes_ano` | periodo | `2026-11` |
| Resumen | Totales del mes: ingresos, gastos, balance, cantidad | `resumen` | estado de cuenta | — |
| Balance | Ingresos − gastos del mes (no depende de las cuentas de dinero) | `balance` | saldo (reservado para una cuenta de dinero, CHG-019) | — |
| Dueño | **Actor** (CHG-017): el Usuario cuya sesión verificada tiene el correo de `OWNER_EMAIL`; sus privilegios extra son ver el Monitor y administrar usuarios desde el panel (CHG-023). Es el **único administrador**: «Administrador» y «Dueño» son el mismo actor (no hay otro rol ni se guarda en la BD). Es distinto del «propietario del registro» (INV-001) | `OWNER_EMAIL` | admin, superusuario, root; usar «propietario del registro» para el dueño de un dato | — |
| Monitor | Página y ruta de solo lectura (`/monitor/resumen`) que muestra al Dueño los consumos de las plataformas y los contadores propios | `monitor` | diagnóstico; «panel de administración» (ese nombre es el de «Panel de usuarios») | — |
| Contador diario | Cantidad agregada por día UTC, métrica y origen de un consumo propio (llamadas y tokens de Claude, correos enviados, mensajes de WhatsApp); sin datos personales | `contadores` | estadística, log de uso | Claude, origen `asistente`, 2026-11-24: 4 llamadas |
| Plataforma | Servicio externo cuyo consumo lee el Monitor: Railway, Anthropic, Meta, Supabase, Vercel o Brevo | `plataformas` | proveedor, servicio (como término oficial) | — |
| Panel de usuarios | (CHG-023) Página `/dashboard/usuarios` y rutas `/admin/*` donde el Dueño lista, busca, suspende, reactiva, cierra sesiones y elimina usuarios y ve el registro de acciones. Solo muestra conteos, nunca datos financieros | `admin_usuarios` | panel de control, backoffice | — |
| Suspender | (CHG-023) Bloquear una cuenta **activa** sin borrarla: no puede iniciar sesión y sus sesiones abiertas dejan de valer al instante, y WhatsApp se desconecta. Se revierte con «Reactivar». No es `is_active = false` (eso es una cuenta pendiente) | `users.suspendida` | bloquear (se usa «bloqueo» para el de login), desactivar, banear | La cuenta suspendida recibe 403 al iniciar sesión |
| Cerrar sesiones | (CHG-023) Hacer que todas las sesiones abiertas de una cuenta dejen de valer (sube la versión de sesión) sin cambiar su contraseña ni su estado | `session_version` | expulsar, desloguear | — |
| Registro de acciones | (CHG-023) Lista de lo que el Dueño hizo desde el panel (acción, id del usuario afectado, fecha), sin datos personales; sobrevive a la baja del usuario | `auditoria_admin` | log, historial (se usa «log» para el del servidor) | `suspender` · `2026-11-25` |
| Último acceso | (CHG-023) Fecha del último **inicio de sesión** del usuario (se guarda como mucho una vez por hora); no es actividad en la app, porque la sesión dura 7 días | `ultimo_acceso` | última actividad, última conexión | — |
| Cuenta de dinero | (CHG-019) Lugar donde la persona tiene dinero, creado a mano: efectivo, ahorros/corriente, billetera digital o tarjeta de crédito. **No** es la cuenta de usuario ni una cuenta bancaria conectada. Es el término oficial **siempre** en la spec, el código y la interfaz de gestión; el menú de la interfaz puede mostrar solo «Cuentas» como título corto. Está **archivada** o **no archivada** (nunca «activa») | `cuentas`, `cuenta_id` | cuenta bancaria (como término), billetera, wallet, «cuenta activa» para una cuenta de dinero | Efectivo, Ahorros Bancolombia, Tarjeta Visa |
| No archivada | (CHG-019) Estado normal de una cuenta de dinero: admite transacciones y transferencias. Es lo contrario de «archivada» | `archivada = false` | activa (reservado a la cuenta de usuario) | — |
| Movimientos | (CHG-019) **Solo** como conjunto: las transacciones y las transferencias entre cuentas de dinero que la persona ve juntas en su lista. Una sola transacción nunca es «un movimiento» | — | movimiento (en singular, para una transacción), operación | La lista de movimientos del mes |
| Saldo | (CHG-019) Dinero actual de una cuenta de dinero: saldo inicial + ingresos − gastos ± transferencias de sus transacciones y transferencias (todas, aunque su fecha sea futura); derivado, en COP, nunca guardado. No confundir con el Balance (ingresos − gastos del mes) | `saldo` | balance (para una cuenta), disponible | 98 500,50 |
| Saldo inicial | (CHG-019) Dinero que la persona dice tener en la cuenta de dinero al crearla; las transacciones anteriores no se cuentan | `saldo_inicial` | apertura, base | 150 000 |
| Archivar | (CHG-019) Congelar una cuenta de dinero (tenga o no transacciones): no admite transacciones ni transferencias nuevas, ni cambios, ni bajas; se puede desarchivar | `archivada` | desactivar, cerrar | — |
| Sin cuenta | (CHG-019) Transacción sin cuenta de dinero (todas las anteriores a CHG-019); no mueve ningún saldo | `cuenta_id` NULL | huérfana | — |
| Transferencia entre cuentas | (CHG-019) Movimiento de dinero entre dos cuentas de dinero propias; **no** es ingreso ni gasto. No confundir con el medio de pago «Transferencia» (cómo se pagó) | `transferencias` | traspaso, movimiento interno | Efectivo → Ahorros: 40 000 |
| Exportación | (CHG-018) Archivo CSV o Excel (.xlsx) con las transacciones de un mes o rango de hasta 12 meses, montos en COP | `exportaciones` | reporte, backup, respaldo | `finanzy-transacciones-2026-11.csv` |
| Estado de autenticación | (CHG-020) Bloqueos de login (5 fallos en una ventana de 24 h → 15 min), códigos de verificación/restablecimiento y ventanas de límites de envío/intentos; persistidos en PostgreSQL con huellas HMAC | `auth_*` | caché de seguridad, sesión | — |
| Huella | (CHG-020) HMAC-SHA256 con clave derivada de `SECRET_KEY` del correo o la IP; es lo único que se guarda de ellos en el estado de autenticación | `clave` | hash del correo, ID de IP | — |
| Moneda de visualización | Moneda en que se muestran los montos (se guardan en COP) | `currency` | divisa | USD |
