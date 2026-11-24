# Glosario (vocabulario controlado)

Usar **solo** estos términos en spec, interfaz y pruebas. En el código se aceptan los nombres técnicos indicados.

| Término oficial | Definición | En código | Términos a evitar | Ejemplo |
|---|---|---|---|---|
| Usuario | Persona con cuenta en Finanzy | `users`, `usuario_id` | cliente, miembro | — |
| Cuenta pendiente | Usuario registrado que aún no verificó su correo | `is_active = false` | cuenta inactiva, no confirmada | Se elimina tras 1 hora |
| Cuenta activa | Usuario que verificó su correo | `is_active = true` | — | Puede iniciar sesión |
| Sesión | Token JWT que identifica al usuario durante 7 días | `access_token` | login, cookie | — |
| Código | Número de 6 dígitos enviado por correo para verificar la cuenta o restablecer la contraseña | `code` | OTP, PIN, token | `482913` |
| Transacción | Movimiento de dinero del usuario | `transacciones` | movimiento, operación, registro | Gasto de 42.50 en Comida |
| Ingreso | Transacción que suma dinero | `tipo = "ingreso"` | entrada, abono (salvo metas) | Salario |
| Gasto | Transacción que resta dinero | `tipo = "gasto"` | egreso, salida, débito | Supermercado |
| Categoría | Agrupación de transacciones de un tipo, propia de cada usuario | `categorias` | rubro, etiqueta | 🍔 Comida |
| Presupuesto | Límite mensual de gasto para una categoría | `presupuestos` | tope, límite (como sustantivo de entidad) | Comida: 500 000 en 2026-11 |
| Meta | Objetivo de ahorro con monto y fecha | `metas` | objetivo, alcancía | Viaje: 3 000 000 para 2027-06 |
| Abono | Aporte de dinero a una meta; genera un gasto en "Ahorro" | `abonar` | depósito, aporte | — |
| Mes | Periodo de consulta en formato `YYYY-MM` | `mes`, `mes_ano` | periodo | `2026-11` |
| Resumen | Totales del mes: ingresos, gastos, balance, cantidad | `resumen` | estado de cuenta | — |
| Balance | Ingresos − gastos del mes | `balance` | saldo | — |
| Dueño | **Actor** (CHG-017): el Usuario cuya sesión verificada tiene el correo de `OWNER_EMAIL`; su único privilegio extra es ver el Monitor. Es distinto del «propietario del registro» (INV-001) | `OWNER_EMAIL` | administrador, admin, superusuario; usar «propietario del registro» para el dueño de un dato | — |
| Monitor | Página y ruta de solo lectura (`/monitor/resumen`) que muestra al Dueño los consumos de las plataformas y los contadores propios | `monitor` | panel de administración, diagnóstico | — |
| Contador diario | Cantidad agregada por día UTC, métrica y origen de un consumo propio (llamadas y tokens de Claude, correos enviados, mensajes de WhatsApp); sin datos personales | `contadores` | estadística, log de uso | Claude, origen `asistente`, 2026-11-24: 4 llamadas |
| Plataforma | Servicio externo cuyo consumo lee el Monitor: Railway, Anthropic, Meta, Supabase, Vercel o Brevo | `plataformas` | proveedor, servicio (como término oficial) | — |
| Moneda de visualización | Moneda en que se muestran los montos (se guardan en COP) | `currency` | divisa | USD |
