# Índice de la especificación

Una línea por elemento. Para leer solo uno (nunca el archivo entero):
`grep -n "^| INV-049" spec/05-INVARIANTS.md` · `grep -n "REQ-F-019" spec/REQUIREMENTS.md` · `grep -n "CT-012" spec/TRACEABILITY.md`.
Contratos, casos de uso, ADR, BDD y flujos son archivos pequeños: léelos completos solo si la tarea los toca.
Se actualiza al añadir o cambiar una invariante, contrato, caso de uso, ADR, BDD o flujo.

## Invariantes (`spec/05-INVARIANTS.md`, fila `| INV-NNN`)
- INV-001: solo el dueño ve, edita o borra sus registros; ajeno o inexistente = 404.
- INV-002: transacción y presupuesto solo usan categorías del mismo usuario.
- INV-003: montos > 0, ≤ 9 999 999 999,99 y 2 decimales; monto ahorrado ≥ 0.
- INV-004: tipo de transacción y categoría solo `ingreso` o `gasto`.
- INV-005: fechas `YYYY-MM-DD` y meses `YYYY-MM`.
- INV-006: cuenta pendiente de verificar nunca obtiene sesión con el login.
- INV-007: código de un solo uso, 10 min, 5 intentos, generado con `secrets`.
- INV-008: abono a meta atómico (gasto y suma juntos o ninguno); meta del usuario.
- INV-009: forgot-password, resend-code y login no revelan si el correo existe.
- INV-010: límites de envío de códigos por correo, destinatario, IP y global diario.
- INV-011: sesiones JWT firmadas con HMAC; exigen `exp` y `sub`.
- INV-012: sin endpoints de diagnóstico en producción.
- INV-013: si la BD falla, error; nunca se guarda en memoria con Supabase configurado.
- INV-014: correo único, comparado y guardado en minúsculas.
- INV-015: contraseñas solo como hash bcrypt; hashes antiguos siguen válidos.
- INV-016: cambiar o restablecer contraseña cierra sesiones y desconecta WhatsApp.
- INV-017: un token solo vale si la cuenta de usuario sigue activa.
- INV-018: contraseña nueva de 8 a 128 caracteres.
- INV-019: configuración segura que nunca impide arrancar (SECRET_KEY, CORS, DEBUG).
- INV-020: el token vive solo en cookie HttpOnly; CSRF y Origin en cambios de datos.
- INV-021: todo registro pertenece a un usuario existente (llaves foráneas CASCADE).
- INV-022: medio de pago opcional y de la lista permitida.
- INV-023: el asistente solo lee y solo datos del usuario del token.
- INV-024: topes de costo y límites del asistente; 503 sin clave de Anthropic.
- INV-025: una recurrente nunca se registra sola; solo al confirmarla la persona.
- INV-026: cada ocurrencia recurrente se registra u omite una sola vez (compare-and-set).
- INV-027: cambiar contraseña desde el perfil exige la actual; error 400, cuenta como fallo.
- INV-028: sin categorías ni presupuestos duplicados (índices UNIQUE).
- INV-029: WhatsApp solo con firma de Meta, número enlazado y código de enlace.
- INV-030: topes de costo y límites de WhatsApp.
- INV-031: Monitor solo accesible al Dueño, verificado en cada petición.
- INV-032: Monitor nunca expone tokens, correos ni datos personales.
- INV-033: Monitor solo lectura; un no-Dueño recibe 404 en cualquier método.
- INV-034: Monitor sin SSRF: hosts y rutas de plataformas fijos en el código.
- INV-035: Monitor con caché de 60 s, límites propios y plazos en consultas externas.
- INV-036: contadores propios solo agregados por día, sin datos personales.
- INV-037: bloqueos, códigos y límites de auth persistentes en PostgreSQL.
- INV-038: contadores de auth atómicos con funciones SQL que bloquean fila o clave.
- INV-039: auth fail-closed: fallo de BD de estado o plazo vencido = 503.
- INV-040: correo e IP solo como huella HMAC; retención y tope en tablas de auth.
- INV-041: almacén en memoria de auth solo fuera de producción y sin Supabase.
- INV-042: exportación solo de las transacciones del usuario de la sesión.
- INV-043: exportación neutraliza texto que empieza por `=`, `+`, `-`, `@`.
- INV-044: exportación con meses válidos, rango acotado y formato csv/xlsx.
- INV-045: archivo exportado fiel: montos en COP tal como se guardan.
- INV-046: propiedad de cuentas de dinero y transferencias verificada en toda operación.
- INV-047: el saldo de una cuenta de dinero se deriva, no se guarda.
- INV-048: cuenta de dinero (no crédito) nunca queda con saldo negativo.
- INV-049: transferencias entre cuentas propias, distintas, activas, monto positivo, atómicas.
- INV-050: cuenta con movimientos no se elimina (409); se archiva.
- INV-051: tope de montos de cuentas de dinero alineado con NUMERIC.
- INV-052: abono, recurrentes, WhatsApp, asistente y exportación con cuenta de dinero.
- INV-053: panel de administración `/admin/*` solo para el Dueño, fail-closed.
- INV-054: el Dueño no puede suspender, eliminar ni cerrar sesiones de sí mismo.
- INV-055: respuestas y logs del panel sin hashes, versión de sesión ni secretos.
- INV-056: suspendida no inicia sesión ni conserva sesiones; reactivar la restaura.
- INV-057: cerrar sesiones sube `session_version` en 1 con una sentencia atómica.
- INV-058: eliminar desde el panel exige confirmar el correo exacto del usuario.
- INV-059: auditoría de cada acción exitosa del administrador, sin datos sensibles.
- INV-060: límites, paginación y búsqueda segura del panel.
- INV-061: `ultimo_acceso` se escribe al emitir sesión, sin bloquear el login.
- INV-062: migración del panel idempotente y sin efectos sobre filas existentes.
- INV-063: fecha de transacción o transferencia dentro de 2026-01-01 a hoy+365; día inexistente = 422.

## Contratos (`spec/CONTRACTS/`)
- CT-001-auth.md: registro, verificación, login, reenvío, recuperar contraseña, proxy y cookie.
- CT-002-usuario.md: `/users/me` ver, nombre, moneda, contraseña, eliminar cuenta, `es_dueno`.
- CT-003-transacciones.md: CRUD de transacciones, resumen del mes, medio de pago, cuenta.
- CT-004-categorias.md: CRUD de categorías y categorías por defecto.
- CT-005-presupuestos.md: presupuestos por mes y categoría, copiar del mes anterior.
- CT-006-metas.md: metas de ahorro, abono atómico, cuenta de dinero opcional.
- CT-007-asistente.md: `POST /asistente/chat`, herramientas de solo lectura, topes.
- CT-008-recurrentes.md: CRUD, pendientes, confirmar y omitir recurrentes.
- CT-009-whatsapp.md: webhook de Meta y enlace del número con código.
- CT-010-monitor.md: `GET /monitor/resumen`, solo Dueño, consumos por plataforma.
- CT-011-exportar.md: `GET /exportaciones/transacciones` csv/xlsx por mes o rango.
- CT-012-cuentas.md: cuentas de dinero y transferencias.
- CT-013-admin-usuarios.md: `/admin/usuarios` y auditoría, solo Dueño.

## Casos de uso (`spec/USE-CASES/`)
- UC-001-registrar-cuenta.md: registro con código por correo.
- UC-002-iniciar-sesion.md: login, bloqueos y cuenta pendiente.
- UC-003-restablecer-contrasena.md: recuperar contraseña con código.
- UC-004-registrar-transaccion.md: crear, editar y borrar transacciones.
- UC-005-gestionar-categorias.md: crear, editar y borrar categorías.
- UC-006-definir-presupuesto-mensual.md: presupuesto por categoría y mes.
- UC-007-crear-meta-y-abonar.md: metas de ahorro y abonos.
- UC-008-consultar-resumen-y-reportes-del-mes.md: resumen, reportes y gráficos del mes.
- UC-009-cambiar-moneda-de-visualizacion.md: moneda mostrada; los montos se guardan en COP.
- UC-010-eliminar-cuenta.md: eliminar la cuenta de usuario y sus datos.
- UC-011-preguntar-al-asistente.md: preguntas en lenguaje natural con Claude.
- UC-012-transacciones-recurrentes.md: gestionar y confirmar recurrentes.
- UC-013-registrar-por-whatsapp.md: ingresos y gastos por WhatsApp con IA.
- UC-014-ver-monitor-de-consumos.md: consumos de plataformas para el Dueño.
- UC-015-exportar-transacciones.md: descargar CSV o Excel.
- UC-016-gestionar-cuentas-y-transferencias.md: cuentas con saldo y transferencias.
- UC-017-administrar-usuarios.md: listar, suspender, cerrar sesiones y eliminar (Dueño).

## Decisiones (`spec/ADR/`)
- ADR-001-stack.md: Next.js + FastAPI + Supabase + Brevo, hospedaje y costos.
- ADR-002-correo-brevo.md: correo por API HTTPS de Brevo (Railway bloquea SMTP).
- ADR-003-seguridad-autenticacion.md: PyJWT, bcrypt y límites de frecuencia.
- ADR-004-sdd-modo-proporcional.md: SDD con 5 agentes y modos por riesgo.
- ADR-005-sesion-cookie-httponly.md: cookie HttpOnly, proxy de Next.js y CSRF.
- ADR-006-asistente-claude.md: asistente con la API de Claude (tool use, solo lectura).
- ADR-007-whatsapp-cloud-api.md: WhatsApp con Cloud API de Meta y agente de escritura limitada.
- ADR-008-monitor-del-dueno.md: monitor de consumos solo para el Dueño.
- ADR-009-cuentas-y-transferencias.md: saldo derivado y transferencias en tabla propia.
- ADR-010-estado-de-autenticacion-persistente.md: bloqueos, códigos y límites en PostgreSQL, fail-closed.
- ADR-011-exportacion-csv-xlsx.md: exportar CSV y Excel con `openpyxl`.
- ADR-012-panel-de-administracion-de-usuarios.md: panel de usuarios solo para el Dueño.

## Escenarios (`spec/BDD/`)
- BDD-AUTH.feature: registro e inicio de sesión (INV-006, 010, 011, 014, 015).
- BDD-AUTH-PERSISTENTE.feature: bloqueos, códigos y límites persistentes (INV-037 a 041).
- BDD-LIMITES.feature: límites contra abuso de correos (INV-010).
- BDD-RECUPERACION.feature: recuperar contraseña (INV-007, 009, 016).
- BDD-PROPIEDAD.feature: aislamiento de datos entre usuarios (INV-001, 002).
- BDD-TRANSACCIONES.feature: transacciones y resumen (INV-003 a 005).
- BDD-METAS.feature: metas de ahorro y abono (INV-008).
- BDD-RECURRENTES.feature: transacciones recurrentes (INV-025, 026).
- BDD-WHATSAPP.feature: registrar por WhatsApp con IA (INV-029, 030).
- BDD-MONITOR.feature: Monitor solo para el Dueño (INV-031 a 036).
- BDD-EXPORTAR.feature: exportar a CSV o Excel (INV-042 a 045).
- BDD-CUENTAS.feature: cuentas de dinero y transferencias (INV-046 a 052).
- BDD-ADMIN-USUARIOS.feature: administración de usuarios del Dueño (INV-053 a 062).

## Flujos (`spec/WORKFLOWS/`)
- WF-001-registro-y-verificacion.md: registro y verificación por correo paso a paso.
- WF-002-abono-a-meta.md: abono a meta con compensación si falla.

## Dominio y otros
- `01-GLOSSARY.md` términos (cuenta de usuario vs cuenta de dinero) · `02-ENTITIES.md` entidades · `03-VALUE-OBJECTS.md` valores · `04-STATES.md` estados · `NFR/NFR.md` no funcionales (REQ-N-NNN).
- `REQUIREMENTS.md` (REQ-F/REQ-N) y `TRACEABILITY.md` (REQ → UC → CT → código → prueba): solo con `grep -n "REQ-F-0NN"`.
