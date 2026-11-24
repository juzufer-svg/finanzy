# CHG-020 — Persistir los bloqueos de login en PostgreSQL

- **Estado:** en especificación (spec escrita, pendiente de validación y de aprobación del dueño; sin código)
- **Fecha:** 2026-11-24 · **Solicitante:** Julián Zúñiga (dueño)
- **Riesgo:** alto · **Modo:** completo (seguridad) · **BL:** BL-039 (cierra BL-014 en lo que toca a login y códigos de correo)

## 1. Pedido original (literal, sin reinterpretar)
> 3. Persistir los bloqueos de login en PostgreSQL: cierra la deuda de seguridad más importante.

Contexto: el dueño pidió mejoras para Finanzy y eligió implementar inicialmente estas tres: «1. Exportar a Excel/CSV: rápido, útil y de bajo riesgo. 2. Cuentas con saldo y transferencias: es lo que más cambia la utilidad diaria. 3. Persistir los bloqueos de login en PostgreSQL: cierra la deuda de seguridad más importante.»

## 2. Clasificación
Tipo: seguridad / deuda técnica (sin función nueva para la persona usuaria). Riesgo: **alto**. Modo: **completo** (toca seguridad, autenticación, infraestructura de datos y una migración SQL).
Cambia de spec: INV-007, INV-009, INV-010, INV-013 (se **aclaran**, no se debilitan), nuevas INV-037 a INV-041, CT-001 (nuevo 503), UC-002/UC-003 (flujo alterno), 04-STATES (Código ya no «desaparece» al reiniciar), ADR-010, NFR REQ-N-016 a REQ-N-018. No hay REQ funcional nuevo: es deuda de REQ-F-001/002/003 y REQ-N-002 (se anota en cada uno).

## 3. Análisis
**Estado actual (leído en el código, 2026-11-24):**
- `be/api/routes/auth.py`: `_login_fails` (dict en memoria, línea ~30) y cuatro `SlidingWindow` en memoria: `_ip_email_requests` (10/h por IP), `_email_daily` (10/día por destinatario), `_global_daily` (250/día), `_ip_auth_attempts` (30 / 10 min por IP).
- `be/utils/email.py`: `_pending_codes` (dict en memoria) con el código **en claro**, vencimiento e intentos.
- `be/api/routes/users.py::change_password` usa `_check_locked`, `_register_fail`, `_login_fails.pop` y `_limit_ip_for_auth` (cambio de contraseña desde el perfil, INV-027).
- Efecto: cada despliegue o reinicio de Railway **borra** bloqueos, códigos pendientes y contadores de envío; un atacante puede forzar el reinicio de la cuenta de fallos esperando un despliegue, y con varias instancias cada una tendría su propio contador. Además, **incumple en espíritu INV-013** («nunca se guardan datos en memoria cuando Supabase está configurado»): hoy hay estado de seguridad en memoria con Supabase activo. Se aclara INV-013 para que cubra explícitamente el estado de autenticación (ADR-010).

**Alcance (aprobado por el dueño):** SOLO login y códigos de correo: `auth.py`, `utils/email.py` y `core/rate_limit.py` para esos usos (más los dos puntos de `users.py` que reutilizan el bloqueo, INV-027, y la baja de cuenta, REQ-F-013). Fuera de alcance (deuda BL-040): limitadores en memoria del asistente (INV-024), de WhatsApp (INV-030, `_intentos_codigo` del enlace de número) y del Monitor (INV-035); la caché del Monitor.

**Diseño (resumen; detalle en ADR-010):** tres tablas nuevas en PostgreSQL con RLS sin políticas (`auth_login_intentos`, `auth_codigos`, `auth_limites_eventos`) y funciones SQL atómicas solo para `service_role`. Claves por huella HMAC-SHA256 (correo e IP nunca en claro), códigos solo como HMAC, purga a 30 días y borrado al eliminar la cuenta. **Fail-closed:** si la BD de estado falla o tarda más de 5 s, 503; nunca se «deja pasar» ni se cae a memoria con Supabase configurado. Sin Supabase (modo demo) sigue en memoria **solo fuera de producción**.

**Riesgos y cómo se cubren:**
| Riesgo | Cobertura |
|---|---|
| Peticiones paralelas esquivan el contador (comprobar y luego sumar no es atómico) | INV-038: el intento se **reserva** en la BD (función con bloqueo de fila) antes de comprobar la contraseña; prueba real en PostgreSQL (`07_comprobar_auth_persistente.sql` + `probar.sh`) |
| Códigos en claro en respaldos de la BD | INV-040: solo HMAC con clave derivada de `SECRET_KEY` (que no está en la BD) |
| Correo e IP son datos personales | INV-040: solo huellas HMAC; purga a 30 días; baja de cuenta borra intentos y códigos |
| Filas huérfanas al borrar la cuenta | INV-040 (borrado por huella en `DELETE /users/me`); las que queden se purgan a 30 días |
| BD de estado caída = nadie entra | Aceptado y deseado (fail-closed, INV-039); ya no se podía iniciar sesión sin la BD de usuarios |
| Enumeración de cuentas por diferencias de respuesta, de fallo o de tiempo (INV-009) | INV-039/INV-009: `forgot-password` y `resend-code` hacen las mismas llamadas a la BD de estado exista o no la cuenta (código señuelo que nunca se envía) |
| Latencia por llamadas extra | REQ-N-017: ≤ 3 llamadas por intento de login; ejecutadas en hilo para no bloquear el servidor |
| Migración no aplicada antes de desplegar → todo el login responde 503 | Orden de despliegue obligatorio: **SQL primero**, backend después (se anota en el cierre) |
| Rotar `SECRET_KEY` cambia las huellas | Efecto: se pierden bloqueos y códigos pendientes (las sesiones ya se invalidan igual). Aceptado y documentado en ADR-010 |

## 4. Preguntas abiertas
| # | Pregunta | Impacto | Respuesta | Quién |
|---|---|---|---|---|
| 1 | Alcance: ¿solo login y códigos de correo? | Alcance | Sí: `auth.py`, `utils/email.py` y `core/rate_limit.py` para esos usos (2026-11-24) | Julián Zúñiga |
| 2 | Si la BD falla, ¿el login responde error o deja pasar? | Seguridad | Responde error: **503, fail-closed** (2026-11-24) | Julián Zúñiga |
| 3 | ¿Los despliegues deben dejar de borrar bloqueos y códigos vigentes? | Seguridad | Sí (2026-11-24) | Julián Zúñiga |
| 4 | Almacenamiento: tablas PostgreSQL nuevas con RLS sin políticas y funciones SQL atómicas; clave por huella HMAC del correo (y de la IP); códigos solo como HMAC; mismos números de INV-007/009/010 (5 fallos/15 min, 5 intentos por código, 10 correos/día por destinatario, 250 en total, 10 pedidos/h y 30 intentos/10 min por IP) | Diseño/seguridad | **Decidido por defecto seguro del coordinador; el dueño puede cambiarlo** | coordinador |
| 5 | Purga a 30 días (oportunista, una vez al día, sin tarea programada) y borrado de intentos y códigos al eliminar la cuenta | Datos/privacidad | **Decidido por defecto seguro; el dueño puede cambiarlo.** Los eventos de límites (huella, hora) **no** se borran al eliminar la cuenta: hacerlo permitiría reiniciar el tope «10 correos/día» registrando de nuevo el mismo correo; expiran por la purga | coordinador |
| 6 | Fail-closed también para los límites por IP; plazo total de 5 s por operación de estado | Seguridad | **Decidido por defecto seguro; el dueño puede cambiarlo** (5 s, coherente con INV-034) | coordinador |
| 7 | Modo demo (sin Supabase): en memoria solo fuera de producción; en producción sin Supabase → 503 | Seguridad | **Decidido por defecto seguro** (INV-013 aclarada, INV-041) | coordinador |
| 8 | ¿Los 5 fallos se cuentan en una ventana de 15 min desde el primer fallo, o sin caducidad hasta el bloqueo (como hoy)? En memoria el contador «caducaba» con cada reinicio; persistido sin caducidad podría bloquear a quien falla 1 vez al mes | Seguridad/uso | **Decidido por defecto seguro; el dueño puede cambiarlo:** ventana de 15 min desde el primer fallo de la serie; al 5.º fallo, bloqueo de 15 min contados desde ese fallo; un inicio de sesión correcto reinicia la cuenta. Es la lectura literal de «5 fallos/15 min» y no relaja el bloqueo | coordinador |
| 9 | Orden en cada intento de login: **reservar** el intento antes de comprobar la contraseña (y devolverlo si es correcta) | Seguridad | **Decidido por defecto seguro:** así N peticiones paralelas no comprueban más de 5 contraseñas (INV-038) | coordinador |
| 10 | Las huellas dependen de `SECRET_KEY`; si se rota, bloqueos y códigos pendientes se pierden. Si falta y se genera una temporal (INV-019), el estado persistido pierde valor en cada reinicio | Operación | **Aceptado por defecto:** producción ya exige `SECRET_KEY` fija (las sesiones dependen de ella); el aviso `[CONFIG]` existente cubre el caso. No se añade una variable nueva | coordinador |
| 11 | Despliegue de transición: los códigos pendientes en memoria se pierden en ese único despliegue (nadie los tiene guardados en la BD) | Operación | Aceptado: la persona pide otro código (10 min de vigencia) | coordinador |
| 12 | Falta por confirmar al implementar (técnico, no de negocio): que el cliente de Supabase permita un plazo de 5 s por llamada o que se imponga con `asyncio.wait_for` en un hilo | Implementación | Pendiente de T2; si no es posible, se escala antes de cerrar | generador |

Preguntas que **requieren** respuesta del dueño: ninguna. Las filas 4 a 10 son provisionales y reversibles.

## 5. Spec afectada
`spec/05-INVARIANTS.md` (INV-037 a INV-041; aclaraciones en INV-007, INV-009, INV-010, INV-013), `spec/CONTRACTS/CT-001-auth.md` (503), `spec/ADR/ADR-010-estado-de-autenticacion-persistente.md`, `spec/BDD/BDD-AUTH-PERSISTENTE.feature`, `spec/USE-CASES/UC-002`, `UC-003`, `spec/04-STATES.md`, `spec/02-ENTITIES.md`, `spec/01-GLOSSARY.md`, `spec/NFR/NFR.md` (REQ-N-016 a REQ-N-018), `spec/REQUIREMENTS.md` (§5 notas en REQ-F-001/002/003/013, §9), `spec/TRACEABILITY.md`, `work/BACKLOG.md` (BL-039, BL-014, BL-040) · **Aprobación de la spec:** pendiente

## 6. Plan de tareas
| Tarea | Alcance | Depende de | Estado | Ciclos |
|---|---|---|---|---|
| T1 | Migración `backend/sql/2026-11-24_auth_persistente.sql` (tres tablas con RLS sin políticas, funciones atómicas solo `service_role`, purga) + `backend/sql/pruebas/07_comprobar_auth_persistente.sql` y bloque de concurrencia real en `probar.sh` (6 reservas simultáneas → 5 permitidas; código de un solo uso con 2 sesiones) | spec aprobada | pendiente | 0 |
| T2 | Modelo `be/models/auth_estado.py` (huella HMAC, llamadas RPC en hilo con plazo de 5 s, fail-closed → 503, modo demo en memoria solo fuera de producción) + `be/core/rate_limit.py` (limitador persistente para los usos de auth, sin tocar `SlidingWindow` de los demás) + pruebas del modelo | T1 | pendiente | 0 |
| T3 | Integrar en `auth.py` (login, registro, verificar, reenviar, olvidé, restablecer), `utils/email.py` (códigos), `users.py` (`change_password`, baja de cuenta); código señuelo para INV-009; `backend/tests/test_auth_persistente.py` y adaptación de `conftest.py`, `test_limites.py`, `test_codigos.py`, `test_auth.py` | T2 | pendiente | 0 |
| T4 | Validación (pytest completo repetido, `pip-audit`, CI de SQL), revisión independiente, trazabilidad, nota de despliegue (SQL antes que el backend; sin variables nuevas) | T3 | pendiente | 0 |

Pruebas nombradas (todas en `backend/tests/test_auth_persistente.py` salvo que se indique): ver INV-037 a INV-041 en `spec/05-INVARIANTS.md` y `spec/BDD/BDD-AUTH-PERSISTENTE.feature`.

## 7. Registro de ejecución
| Fecha | Agente | Acción | Resultado / evidencia |
|---|---|---|---|
| 2026-11-24 | coordinador | Pedido registrado | Archivo creado |
| 2026-11-24 | clasificador | Clasificación | alto / completo; hallazgos revisados por el coordinador |
| 2026-11-24 | generador | Especificación (sin código) | REQ/INV/CT/ADR-010/BDD/NFR/TRACEABILITY/BACKLOG escritos; INV-013 incumplida hoy por `_pending_codes` y `_login_fails` (verificado leyendo el código) |

## 8. Cierre
- **Aprobación humana final:** pendiente
