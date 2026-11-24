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
| Dueño (CHG-017) | Actor: Usuario cuya sesión verificada tiene el correo configurado en la variable `OWNER_EMAIL` (no está escrito en el código). No es el «propietario del registro» de INV-001 | Todo lo del Usuario, y además **ver el Monitor de consumos** (solo lectura, REQ-F-018) | Ver datos de otros usuarios (INV-001 sigue igual); ejecutar acciones desde el Monitor |
| Sistema de correo (Brevo) | Servicio externo | Recibir pedidos de envío de códigos | — |

No hay roles de administrador en la app: el único privilegio del Dueño es ver el Monitor de consumos (REQ-F-018).

## 4. Alcance

- **Dentro:** cuentas con verificación por correo, inicio de sesión, recuperación de contraseña, transacciones,
  categorías, presupuestos mensuales, metas de ahorro con abonos, resumen y reportes del mes, moneda de visualización,
  modo oscuro, eliminación de la cuenta.
- **Fuera:** varias personas por cuenta, cuentas bancarias conectadas, importación/exportación de archivos,
  aplicación móvil nativa, notificaciones fuera de la app (correo o push).
- **Ampliación aprobada por el dueño el 2026-11-23 (CHG-012):** transacciones recurrentes que se **proponen** y la
  persona confirma (nunca se registran solas), copiar presupuestos del mes anterior, editar el nombre y cambiar la
  contraseña desde el perfil, página propia de categorías y avisos de presupuesto dentro de la app.
- **Ampliación aprobada por el dueño el 2026-11-24 (CHG-017, REQ-F-018):** Monitor de consumos **solo para el Dueño**,
  de **solo lectura**: contadores propios (Claude, Brevo, WhatsApp) y lectura de las APIs de Railway, Anthropic, Meta,
  Supabase, Vercel y Brevo.
  - **Dentro del Monitor:** ver cifras agregadas de consumo, cuotas y créditos; marcar «no disponible» lo que no se pueda leer.
  - **Fuera del Monitor:** cualquier acción de escritura sobre las plataformas, reiniciar servicios, cambiar variables de
    entorno, borrar, y mostrar datos personales o secretos.

## 5. Requerimientos funcionales

| ID | Requerimiento | Prioridad | Criterios de aceptación | Estado |
|---|---|---|---|---|
| REQ-F-001 | El sistema debe permitir crear una cuenta verificada por correo | Must | CA-1: dado un correo no registrado, al registrarse se crea la cuenta inactiva y se envía un código de 6 dígitos. CA-2: con el código correcto la cuenta se activa y se inicia sesión. CA-3: un correo ya activo devuelve "El correo ya está registrado". CA-4: las cuentas sin verificar se eliminan tras 1 hora | Verificado |
| REQ-F-002 | El sistema debe permitir iniciar sesión con correo y contraseña | Must | CA-1: con credenciales válidas devuelve una sesión (JWT, 7 días). CA-2: con credenciales inválidas responde "Credenciales inválidas". CA-3: una cuenta sin verificar no obtiene sesión y recibe un código. CA-4: tras 5 fallos el correo se bloquea 15 min | Verificado |
| REQ-F-003 | El sistema debe permitir restablecer la contraseña por correo | Must | CA-1: al pedirlo se envía un código si la cuenta existe, con la misma respuesta exista o no. CA-2: con el código correcto y una contraseña de ≥ 8 caracteres se cambia la contraseña y se activa la cuenta. CA-3: el código es de un solo uso. CA-4: al restablecer la contraseña se cierran todas las sesiones abiertas de la cuenta (INV-016) | Verificado |
| REQ-F-004 | El usuario debe poder registrar, editar y eliminar transacciones de ingreso o gasto | Must | CA-1: una transacción tiene monto > 0, tipo, fecha, categoría propia opcional y descripción. CA-2: eliminar pide confirmación. CA-3: no puede tocar transacciones ajenas. CA-4 (CHG-007): puede indicar el medio de pago (Débito, Crédito, Efectivo, Transferencia, Nequi / Daviplata) o dejarlo sin especificar, filtrar por él y ver en Reportes el gasto por medio de pago | Verificado |
| REQ-F-005 | El usuario debe ver las transacciones de un mes y su resumen | Must | CA-1: lista por mes (`YYYY-MM`), agrupada por categoría. CA-2: resumen con ingresos, gastos, balance y cantidad. CA-3: puede navegar entre meses. CA-4 (CHG-006): buscador por descripción o nombre de categoría (sin distinguir tildes ni mayúsculas) y filtro por categoría (incluida "Sin categoría"). CA-5 (CHG-006): el resumen del tablero compara ingresos, gastos y balance con el mes anterior | Verificado |
| REQ-F-006 | El usuario debe poder gestionar sus categorías | Must | CA-1: al primer acceso recibe categorías por defecto. CA-2: puede crear, editar y eliminar categorías propias (nombre, ícono, tipo). CA-3: eliminar pide confirmación. CA-4 (CHG-012): tienen su propia página «Categorías» en el menú. CA-5 (CHG-013): no puede haber dos categorías con el mismo nombre (sin distinguir mayúsculas ni espacios) y tipo (INV-028) | Verificado |
| REQ-F-007 | El usuario debe poder definir presupuestos mensuales por categoría | Must | CA-1: presupuesto = categoría propia + límite > 0 + mes. CA-2: se muestra lo gastado y el avance (≥ 75 % aviso, ≥ 100 % excedido). CA-3: puede editar el límite y eliminar con confirmación. CA-4 (CHG-012): puede copiar los presupuestos del mes anterior al mes que está viendo; los que ya existen en ese mes no se reemplazan ni se duplican. CA-5 (CHG-012): el Inicio avisa de los presupuestos del mes en ≥ 75 % y excedidos. CA-6 (CHG-013): un solo presupuesto por categoría y mes (INV-028) | Verificado |
| REQ-F-008 | El usuario debe poder crear y gestionar metas de ahorro | Must | CA-1: meta = nombre + monto objetivo > 0 + fecha objetivo. CA-2: se muestra el porcentaje completado. CA-3: una meta está completada cuando lo ahorrado ≥ objetivo. CA-4: puede editar y eliminar con confirmación | Verificado |
| REQ-F-009 | El usuario debe poder abonar a una meta | Must | CA-1: un abono suma a lo ahorrado de la meta y registra un gasto en la categoría "Ahorro" (se crea si no existe). CA-2: si la meta no existe o no es suya, no se registra nada | Verificado |
| REQ-F-010 | El usuario debe ver reportes del mes | Should | CA-1: totales de ingresos y gastos, balance, gasto diario promedio y categoría con más gasto. CA-2 (CHG-006): el promedio diario usa los días reales transcurridos (mes completo si ya cerró; hasta hoy si es el mes en curso; "—" si no ha empezado). CA-3: en el mes en curso, proyección al cierre = promedio diario × días del mes, comparada con el presupuesto total (suma de los presupuestos de gasto del mes). CA-4: comparación con el mes anterior en el total y por categoría. CA-5: gráfico del gasto acumulado día a día con el mes anterior y la línea del presupuesto | Implementado |
| REQ-F-011 | El usuario debe poder elegir la moneda de visualización | Should | CA-1: monedas USD, EUR, MXN, ARS, COP, CLP. CA-2: los montos se guardan en COP y se convierten al mostrarlos con tasas actualizadas (caché 4 h, valores de respaldo). CA-3 (CHG-013): los formularios muestran y reciben los montos en la moneda elegida (con su símbolo) y los guardan convertidos a COP con 2 decimales; si al editar no se toca el monto, se conserva el valor original exacto. El Asistente IA sigue respondiendo en COP. CA-4 (CHG-016): la moneda guardada en la cuenta se aplica al iniciar sesión y al entrar al panel, en cualquier navegador o dispositivo; prevalece sobre lo que haya quedado en el navegador y no hace falta volver a elegirla. Si no hay conexión con el servidor se usa la guardada en el navegador | Implementado |
| REQ-F-012 | El usuario debe poder usar modo claro u oscuro | Could | CA-1: la preferencia se recuerda en el navegador y por defecto sigue al sistema | Implementado |
| REQ-F-013 | El usuario debe poder eliminar su cuenta | Must | CA-1: debe escribir su correo para confirmar. CA-2: se eliminan la cuenta y todos sus datos | Implementado |
| REQ-F-014 | El usuario debe ver su perfil | Should | CA-1: muestra nombre y correo; permite cambiar moneda y tema. CA-2 (CHG-012): puede cambiar su nombre (2-100 caracteres). CA-3 (CHG-012): puede cambiar su contraseña escribiendo la actual y la nueva (8-128); se cierran sus sesiones en otros dispositivos y la actual sigue abierta (INV-027) | Implementado |
| REQ-F-016 | El usuario debe poder registrar transacciones recurrentes (CHG-012) | Should | CA-1: una recurrente = tipo + monto > 0 + frecuencia (mensual, quincenal o semanal) + primera fecha, con categoría propia, descripción y medio de pago opcionales. CA-2: cuando llega su fecha aparece como pendiente en el Inicio y en Recurrentes; nunca se registra sola (INV-025). CA-3: al confirmarla se crea una transacción (monto y fecha ajustables) y avanza a la siguiente fecha; puede omitirla sin registrar nada. CA-4: cada fecha se registra una sola vez aunque se toque dos veces (INV-026). CA-5: puede editarla, pausarla, reactivarla y eliminarla (las transacciones ya registradas se conservan) | Verificado |
| REQ-F-017 | El usuario debe poder registrar ingresos y gastos por WhatsApp en lenguaje libre con IA (CHG-014, ADR-007) | Could | CA-1: enlaza su número con un código de un solo uso generado en Perfil (10 min) y puede desconectarlo. CA-2: un mensaje libre («almorcé por 18 mil con débito») registra el o los movimientos sin pedir confirmación, en COP, con categoría propia elegida por la IA (o sin categoría), fecha (hoy por defecto) y medio de pago; responde con el detalle. CA-3: si falta el monto, pregunta y no registra. CA-4: «deshacer» y correcciones afectan solo lo último registrado por WhatsApp. CA-5: solo el número enlazado puede usarlo y lo propuesto por la IA se valida (INV-029). CA-6: tope de 50 mensajes por día (INV-030). CA-7: cambiar o restablecer la contraseña desconecta WhatsApp (INV-016) | En revisión (verificado con Meta y Claude simulados; falta la prueba real del dueño) |
| REQ-F-018 | El dueño debe poder ver un Monitor de consumos de las plataformas que usa la app (CHG-017, ADR-008) | Could | CA-1: solo el dueño (correo de la variable `OWNER_EMAIL`, comparado en minúsculas y sin espacios, contra el correo de la sesión verificada) ve el Monitor; cualquier otro usuario, o sin sesión, y también cualquier fallo al autorizar (BD caída, sesión inválida), recibe 404 fail-closed (idéntico al de una ruta inexistente, sin `no-store`) y no se revela que el Monitor existe ni cuál es el correo del Dueño; sin `OWNER_EMAIL` configurado se niega a todos (INV-031). La interfaz muestra el enlace «Monitor» solo si el campo booleano `es_dueno` de `GET /users/me` es `true` (solo informa a cada usuario sobre sí mismo; `false` por defecto; CT-002) y la página muestra «no encontrada» si el backend responde 404. CA-2: es de solo lectura (únicamente GET), sin acciones: un no-Dueño con cualquier método (salvo el preflight OPTIONS, que atiende el middleware CORS) recibe el mismo 404, HEAD cuenta como método no GET, y el Dueño con un método distinto de GET recibe 405 con `no-store` (INV-033). CA-3: contadores propios en Supabase, agregados por día y sin correos, teléfonos, textos ni ids de usuario: llamadas y tokens de entrada/salida de Claude (origen `asistente` o `whatsapp`), correos de Brevo enviados con éxito, mensajes de WhatsApp enviados y recibidos (solo de números enlazados); cuentan desde su activación (sin histórico), se conservan 90 días y la respuesta muestra los últimos 30 (INV-036). CA-4: lectura de Railway, Anthropic, Meta, Supabase, Vercel y Brevo con tokens propios del Monitor (variables `MONITOR_*_TOKEN`), distintos de los de envío o escritura y creados con el menor permiso que la plataforma ofrezca (si no permite solo lectura, se documenta en ADR-008 y se verifica por revisión de configuración, no por prueba automatizada); los datos de cada plataforma siguen un esquema de lista blanca (CT-010, INV-032); cada plataforma se muestra «no disponible» si no hay token o la consulta falla, sin romper las demás; nunca se muestran tokens (INV-032, INV-034). CA-5: basta la sesión normal del dueño, sin reautenticar | Especificado (CHG-017, en implementación) |
| REQ-F-015 | El usuario debe poder preguntar en lenguaje natural por sus finanzas (asistente con Claude, CHG-010) | Could | CA-1: responde preguntas sobre totales del mes, movimientos más altos, categorías y presupuestos, medios de pago, búsquedas por texto y metas, usando solo sus datos. CA-2: el asistente no puede crear, editar ni borrar nada (INV-023). CA-3: entiende preguntas de seguimiento dentro de la misma conversación. CA-4: hay topes de uso para controlar el costo (INV-024) | Verificado |

## 6. Requerimientos no funcionales

Detalle medible en `NFR/NFR.md`.

| ID | Categoría | Requerimiento |
|---|---|---|
| REQ-N-001 | Seguridad | Aislamiento total de datos entre usuarios (INV-001, INV-002) |
| REQ-N-002 | Seguridad | Protección contra fuerza bruta y abuso de envío de correos (INV-010) |
| REQ-N-003 | Seguridad | Sin secretos en código, logs ni frontend; sin endpoints de diagnóstico (INV-012), **salvo el Monitor del Dueño (REQ-F-018), que no lo es**: exige sesión del Dueño, responde 404 fail-closed a los demás, es de solo lectura y tampoco expone secretos (INV-031 a INV-033) |
| REQ-N-011 a REQ-N-015 | Seguridad / Datos / Rendimiento | Parámetros medibles del Monitor (timeout, caché, límite de frecuencia, retención, tiempo de respuesta): ver `NFR/NFR.md` |
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
| WhatsApp Cloud API (Meta) | Meta → Railway (webhook) y Railway → Meta | Mensajes de texto del número enlazado y respuestas | CT-009, ADR-007 |
| API de Claude (Anthropic) | Railway → Anthropic | Pregunta o mensaje, categorías del usuario (sin correo, teléfono ni ids) | CT-007, CT-009 |
| APIs de consumo de Railway, Anthropic, Meta, Supabase, Vercel y Brevo (CHG-017) | Railway → cada plataforma, solo lectura | Cifras de uso y consumo agregadas; tokens propios del Monitor | CT-010, ADR-008 |

## 9. Preguntas abiertas y ambigüedades

| # | Pregunta / ambigüedad | Afecta a | Respuesta | Estado |
|---|---|---|---|---|
| 1 | La contraseña de registro exige 6 caracteres y la de recuperación 8. ¿Unificar en 8? | REQ-F-001, REQ-F-003 | Sí, 8-128 en ambos (INV-018, CHG-002); el dueño delegó la decisión el 2026-11-22. Las contraseñas existentes siguen sirviendo | Resuelta |
| 2 | El "gasto diario promedio" divide siempre entre 30 días. ¿Usar los días reales del mes (o los transcurridos si es el mes actual)? | REQ-F-010 | Sí: días reales transcurridos (REQ-F-010 CA-2). Lo pidió el dueño el 2026-11-22 (CHG-006) | Resuelta |
| 3 | La columna `metas.estado` existe en la BD pero la API no la usa; "completada" se deriva de los montos. ¿Eliminar la columna o darle uso (p. ej. cancelar metas)? | REQ-F-008 | — | Abierta |
| 4 | Cambiar la contraseña no cierra las sesiones abiertas. ¿Debe hacerlo? | REQ-F-003 | Sí: versión de sesión por usuario (INV-016, CHG-001), aprobado por el dueño el 2026-11-22 | Resuelta |
| 5 | Supabase gratis se pausa y no tiene respaldos. ¿Tarea programada de actividad + respaldo semanal? | REQ-N-007, REQ-N-008 | Recomendado: sí | Abierta (backlog) |
| 6 | (CHG-017) Valores del Monitor: caché 60 s, 20 peticiones/min, timeout 5 s, ventana de 30 días, «recibidos» solo de números enlazados, purga al escribir | REQ-F-018, REQ-N-011 a N-015 | Decididos por el coordinador por defecto seguro; el dueño puede cambiarlos (CHG-017 §4, preguntas 6 a 10) | Resuelta provisional |
| 7 | (CHG-017) Campos exactos de `datos` por plataforma y ids de configuración | REQ-F-018, CT-010 | Esquema mínimo definido en CT-010; los campos exactos se confirman contra cada API al implementar y todo ajuste se registra en CT-010 antes del cierre | Abierta |
| 8 | (CHG-017) Plataformas que no ofrezcan token de solo lectura (p. ej. Anthropic exige clave de administración) | REQ-F-018 CA-4 | Se documenta en ADR-008 y se verifica por revisión de configuración; lo que no se pueda leer queda «no disponible» | Abierta (se cierra al crear los tokens) |
| 9 | (CHG-017) Riesgo aceptado: correo del Dueño re-registrado por otra persona tras eliminar la cuenta; mitigación opcional (id de usuario fijo o reautenticación) | REQ-F-018 CA-5 | No se implementa; deuda anotada en ADR-008 | Abierta (deuda) |
| 10 | (CHG-017, pregunta 15) ¿`no-store` en el 404 bajo `/monitor/*`? | REQ-F-018, INV-031, INV-035 | **Decidido por el coordinador (por defecto seguro; el Dueño puede cambiarlo):** el 404 del no-Dueño es byte a byte idéntico al de una ruta inexistente, sin `no-store`; `no-store` solo en 200, 405, 429 y 503 del Dueño | Decidida |
| 11 | (CHG-017, preguntas 16 a 20) Preflight OPTIONS fuera de INV-033 (lo atiende el CORS); HEAD cuenta como no GET; campo `es_dueno` en `GET /users/me`; resumen < 6 s con plazo total de 5 s por plataforma y fallos en caché 15 s; purga con marca en la tabla; 405 cuenta para el límite | REQ-F-018, REQ-N-011, REQ-N-015, CT-002, CT-010 | Decididas por el coordinador (por defecto seguro; el Dueño puede cambiarlas) | Resuelta provisional |
