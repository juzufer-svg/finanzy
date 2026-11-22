# REQUIREMENTS — Finanzy

> Qué necesita el usuario. Estado del documento: **APROBADO como línea base** (especificación reconstruida a partir
> del sistema en producción, noviembre de 2026). Cambios futuros: vía `/sdd-nuevo-cambio`.

## 1. Solicitud original

> Necesito mejorar constantemente la app para el control de mis finanzas que ya tengo creada en Vercel.com donde alojo
> mi Front, railway.com donde alojo mi Backend, Supabase.com donde alojo mi base de datos y Brevo.com mi servicio de
> correo gratuito.

(La app existía antes de adoptar SDD; esta spec documenta su comportamiento actual como punto de partida.)

## 2. Problema de negocio

Una persona quiere controlar sus finanzas personales: saber cuánto entra y sale cada mes, en qué categorías gasta,
si respeta los límites que se pone y cómo avanza hacia sus metas de ahorro, desde el navegador y el celular.

## 3. Actores y permisos

| Actor | Descripción | Puede | No puede |
|---|---|---|---|
| Visitante | Persona sin sesión | Ver la página de inicio, registrarse, iniciar sesión, recuperar contraseña | Ver o modificar datos financieros |
| Usuario | Persona con cuenta verificada y sesión activa | Gestionar **sus propios** datos (transacciones, categorías, presupuestos, metas, perfil) | Ver o modificar datos de otro usuario (INV-001) |
| Sistema de correo (Brevo) | Servicio externo | Recibir pedidos de envío de códigos | — |

No hay roles de administrador en la app.

## 4. Alcance

- **Dentro:** cuentas con verificación por correo, inicio de sesión, recuperación de contraseña, transacciones,
  categorías, presupuestos mensuales, metas de ahorro con abonos, resumen y reportes del mes, moneda de visualización,
  modo oscuro, eliminación de la cuenta.
- **Fuera:** varias personas por cuenta, cuentas bancarias conectadas, importación/exportación de archivos,
  transacciones recurrentes, aplicación móvil nativa, notificaciones.

## 5. Requerimientos funcionales

| ID | Requerimiento | Prioridad | Criterios de aceptación | Estado |
|---|---|---|---|---|
| REQ-F-001 | El sistema debe permitir crear una cuenta verificada por correo | Must | CA-1: dado un correo no registrado, al registrarse se crea la cuenta inactiva y se envía un código de 6 dígitos. CA-2: con el código correcto la cuenta se activa y se inicia sesión. CA-3: un correo ya activo devuelve "El correo ya está registrado". CA-4: las cuentas sin verificar se eliminan tras 1 hora | Verificado |
| REQ-F-002 | El sistema debe permitir iniciar sesión con correo y contraseña | Must | CA-1: con credenciales válidas devuelve una sesión (JWT, 7 días). CA-2: con credenciales inválidas responde "Credenciales inválidas". CA-3: una cuenta sin verificar no obtiene sesión y recibe un código. CA-4: tras 5 fallos el correo se bloquea 15 min | Verificado |
| REQ-F-003 | El sistema debe permitir restablecer la contraseña por correo | Must | CA-1: al pedirlo se envía un código si la cuenta existe, con la misma respuesta exista o no. CA-2: con el código correcto y una contraseña de ≥ 8 caracteres se cambia la contraseña y se activa la cuenta. CA-3: el código es de un solo uso. CA-4: al restablecer la contraseña se cierran todas las sesiones abiertas de la cuenta (INV-016) | Verificado |
| REQ-F-004 | El usuario debe poder registrar, editar y eliminar transacciones de ingreso o gasto | Must | CA-1: una transacción tiene monto > 0, tipo, fecha, categoría propia opcional y descripción. CA-2: eliminar pide confirmación. CA-3: no puede tocar transacciones ajenas. CA-4 (CHG-007): puede indicar el medio de pago (Débito, Crédito, Efectivo, Transferencia, Nequi / Daviplata) o dejarlo sin especificar, filtrar por él y ver en Reportes el gasto por medio de pago | Verificado |
| REQ-F-005 | El usuario debe ver las transacciones de un mes y su resumen | Must | CA-1: lista por mes (`YYYY-MM`), agrupada por categoría. CA-2: resumen con ingresos, gastos, balance y cantidad. CA-3: puede navegar entre meses. CA-4 (CHG-006): buscador por descripción o nombre de categoría (sin distinguir tildes ni mayúsculas) y filtro por categoría (incluida "Sin categoría"). CA-5 (CHG-006): el resumen del tablero compara ingresos, gastos y balance con el mes anterior | Verificado |
| REQ-F-006 | El usuario debe poder gestionar sus categorías | Must | CA-1: al primer acceso recibe categorías por defecto. CA-2: puede crear, editar y eliminar categorías propias (nombre, ícono, tipo). CA-3: eliminar pide confirmación | Verificado |
| REQ-F-007 | El usuario debe poder definir presupuestos mensuales por categoría | Must | CA-1: presupuesto = categoría propia + límite > 0 + mes. CA-2: se muestra lo gastado y el avance (≥ 75 % aviso, ≥ 100 % excedido). CA-3: puede editar el límite y eliminar con confirmación | Verificado |
| REQ-F-008 | El usuario debe poder crear y gestionar metas de ahorro | Must | CA-1: meta = nombre + monto objetivo > 0 + fecha objetivo. CA-2: se muestra el porcentaje completado. CA-3: una meta está completada cuando lo ahorrado ≥ objetivo. CA-4: puede editar y eliminar con confirmación | Verificado |
| REQ-F-009 | El usuario debe poder abonar a una meta | Must | CA-1: un abono suma a lo ahorrado de la meta y registra un gasto en la categoría "Ahorro" (se crea si no existe). CA-2: si la meta no existe o no es suya, no se registra nada | Verificado |
| REQ-F-010 | El usuario debe ver reportes del mes | Should | CA-1: totales de ingresos y gastos, balance, gasto diario promedio y categoría con más gasto. CA-2 (CHG-006): el promedio diario usa los días reales transcurridos (mes completo si ya cerró; hasta hoy si es el mes en curso; "—" si no ha empezado). CA-3: en el mes en curso, proyección al cierre = promedio diario × días del mes, comparada con el presupuesto total (suma de los presupuestos de gasto del mes). CA-4: comparación con el mes anterior en el total y por categoría. CA-5: gráfico del gasto acumulado día a día con el mes anterior y la línea del presupuesto | Implementado |
| REQ-F-011 | El usuario debe poder elegir la moneda de visualización | Should | CA-1: monedas USD, EUR, MXN, ARS, COP, CLP. CA-2: los montos se guardan en COP y se convierten al mostrarlos con tasas actualizadas (caché 4 h, valores de respaldo) | Implementado |
| REQ-F-012 | El usuario debe poder usar modo claro u oscuro | Could | CA-1: la preferencia se recuerda en el navegador y por defecto sigue al sistema | Implementado |
| REQ-F-013 | El usuario debe poder eliminar su cuenta | Must | CA-1: debe escribir su correo para confirmar. CA-2: se eliminan la cuenta y todos sus datos | Implementado |
| REQ-F-014 | El usuario debe ver su perfil | Should | CA-1: muestra nombre y correo; permite cambiar moneda y tema | Implementado |
| REQ-F-015 | El usuario debe poder preguntar en lenguaje natural por sus finanzas (asistente con Claude, CHG-010) | Could | CA-1: responde preguntas sobre totales del mes, movimientos más altos, categorías y presupuestos, medios de pago, búsquedas por texto y metas, usando solo sus datos. CA-2: el asistente no puede crear, editar ni borrar nada (INV-023). CA-3: entiende preguntas de seguimiento dentro de la misma conversación. CA-4: hay topes de uso para controlar el costo (INV-024) | Verificado |

## 6. Requerimientos no funcionales

Detalle medible en `NFR/NFR.md`.

| ID | Categoría | Requerimiento |
|---|---|---|
| REQ-N-001 | Seguridad | Aislamiento total de datos entre usuarios (INV-001, INV-002) |
| REQ-N-002 | Seguridad | Protección contra fuerza bruta y abuso de envío de correos (INV-010) |
| REQ-N-003 | Seguridad | Sin secretos en código, logs ni frontend; sin endpoints de diagnóstico (INV-012) |
| REQ-N-004 | Seguridad | Dependencias sin vulnerabilidades conocidas |
| REQ-N-005 | Accesibilidad | Formularios etiquetados, uso con teclado, mensajes anunciados a lectores de pantalla |
| REQ-N-006 | Costo | Operar con US$5/mes (solo Railway Hobby) |
| REQ-N-007 | Disponibilidad | La app no debe quedar fuera de línea por inactividad de la base de datos |
| REQ-N-008 | Recuperación | Respaldo periódico de los datos |
| REQ-N-009 | Calidad | Lint del frontend sin problemas y pruebas del backend pasando antes de desplegar |

## 7. Restricciones

- Presupuesto mínimo: planes gratuitos salvo Railway Hobby (US$5/mes).
- Railway Hobby bloquea SMTP: el correo debe enviarse por API HTTPS (Brevo).
- Brevo gratis: 300 correos/día. Supabase gratis: pausa tras 7 días sin actividad, sin respaldos restaurables.
- Interfaz en español.

## 8. Sistemas externos e integraciones

| Sistema | Dirección | Datos | Contrato |
|---|---|---|---|
| Supabase (PostgreSQL) | Backend → Supabase | Todas las tablas | Cliente supabase-py con clave service_role |
| Brevo | Backend → Brevo | Correo destino, asunto, HTML/texto con el código | `POST https://api.brevo.com/v3/smtp/email` |
| open.er-api.com | Navegador → API | Tasas de cambio respecto a USD | `GET /v6/latest/USD` |
| Vercel | Navegador → Vercel → Railway | Proxy `/api/v1/*` | Rewrite en `next.config.js` |

## 9. Preguntas abiertas y ambigüedades

| # | Pregunta / ambigüedad | Afecta a | Respuesta | Estado |
|---|---|---|---|---|
| 1 | La contraseña de registro exige 6 caracteres y la de recuperación 8. ¿Unificar en 8? | REQ-F-001, REQ-F-003 | Sí, 8-128 en ambos (INV-018, CHG-002); el dueño delegó la decisión el 2026-11-22. Las contraseñas existentes siguen sirviendo | Resuelta |
| 2 | El "gasto diario promedio" divide siempre entre 30 días. ¿Usar los días reales del mes (o los transcurridos si es el mes actual)? | REQ-F-010 | Sí: días reales transcurridos (REQ-F-010 CA-2). Lo pidió el dueño el 2026-11-22 (CHG-006) | Resuelta |
| 3 | La columna `metas.estado` existe en la BD pero la API no la usa; "completada" se deriva de los montos. ¿Eliminar la columna o darle uso (p. ej. cancelar metas)? | REQ-F-008 | — | Abierta |
| 4 | Cambiar la contraseña no cierra las sesiones abiertas. ¿Debe hacerlo? | REQ-F-003 | Sí: versión de sesión por usuario (INV-016, CHG-001), aprobado por el dueño el 2026-11-22 | Resuelta |
| 5 | Supabase gratis se pausa y no tiene respaldos. ¿Tarea programada de actividad + respaldo semanal? | REQ-N-007, REQ-N-008 | Recomendado: sí | Abierta (backlog) |
