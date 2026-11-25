# CHG-023 — Panel de administración de usuarios (solo dueño)

- **Estado:** spec **aprobada por el dueño** (2026-11-25) con las correcciones del validador y sus decisiones sobre P1/P2 (§4). **T1 (SQL) y T4 (frontend) hechas**; T2, T3 y T5 pendientes.
- **Fecha:** 2026-11-25 · **Solicitante:** Julián Zúñiga (dueño) · **Riesgo:** alto · **Modo:** completo · **BL:** BL-042
- **Despliegue (cuando se implemente):** el SQL `backend/sql/2026-11-25_admin_usuarios.sql` va **antes** que el backend (sin la columna `suspendida`, `get_session_version` fallaría y todas las sesiones darían 503); sin variables nuevas (`OWNER_EMAIL` ya existe).

## 1. Pedido original (literal, sin reinterpretar)
> ok ahora necesito implementar un panel basico de administracion de usuarios para tener control de toods los que se registran que sea bein compleot. cualquier duda me preguntas.

## 2. Respuestas del dueño (2026-11-25)
- **Acciones:** ver lista y buscar · suspender y reactivar · cerrar sesiones · eliminar cuenta y todos sus datos.
- **Datos por usuario:** básicos (correo, nombre, fecha de registro, estado, moneda) · uso agregado (cantidades; nunca montos ni descripciones) · último acceso.
- **Auditoría:** registro de acciones del administrador.

## 3. Decisiones por defecto del coordinador (**provisionales**; el dueño puede cambiarlas)
Las de la fila 1 a 7 vienen del encargo del coordinador; las 8 a 16 las propone quien redactó la spec para cerrar huecos y quedan igual de provisionales.
| # | Decisión | Dónde queda |
|---|---|---|
| 1 | Acceso igual al Monitor: solo el correo de `OWNER_EMAIL`, 404 para cualquier otro, fail-closed (INV-031) | INV-053, CT-013 |
| 2 | El propio dueño no puede suspenderse ni eliminarse desde el panel (se extiende a cerrar sus propias sesiones) | INV-054 |
| 3 | Suspensión con columna nueva `suspendida` (no `is_active`: la limpieza de cuentas sin verificar la borraría y `reset-password` la reactivaría) | ADR-012 (2), INV-056 |
| 4 | `ultimo_acceso` se guarda al iniciar sesión **en segundo plano tras responder** (`BackgroundTasks`, decidido por el dueño), como mucho una escritura por hora y usuario; su fallo no rompe ni retrasa el login | INV-061 |
| 5 | Auditoría en tabla propia sin datos personales (id del afectado, acción, fecha), sin llave foránea; sobrevive a la baja | INV-059 |
| 6 | Eliminar exige escribir el correo **y la contraseña del Dueño** (bcrypt en el ejecutor propio, mismo bloqueo por intentos que el login; decidido por el dueño) y reutiliza la baja existente (REQ-F-013: cascada, `auth_borrar_de_cuenta`, WhatsApp) | INV-058 |
| 7 | Página nueva `/dashboard/usuarios`, visible solo con `es_dueno` | REQ-F-021 CA-1 |
| 8 | **Un solo administrador**, deducido del correo (sin rol guardado ni tabla de administradores) | glosario, REQUIREMENTS §3 |
| 9 | La validación de parámetros y cuerpo corre **después** de autorizar (despachador ASGI propio): un no-Dueño no puede ver un 422 | INV-053, ADR-012 (1) |
| 10 | Suspender: sube `session_version` + marca `suspendida` + borra el enlace de WhatsApp en **una transacción**; `usuario_de_sesion` rechaza `suspendida` (401) leyendo la columna en la misma consulta; 403 genérico en el login **solo** con contraseña correcta; `verify-email` no emite sesión a una suspendida; solo se suspende una cuenta **activa** | INV-056, CT-001 |
| 11 | Cerrar sesiones también desconecta WhatsApp (coherente con INV-016) | INV-057 |
| 12 | Acciones atómicas con su auditoría en funciones SQL (`admin_*`); eliminar = función atómica (auditoría + borrado) y después limpieza de autenticación best-effort; no se usa `UserDB.delete_by_id` (oculta errores) | INV-058, ADR-012 (5, 6) |
| 13 | Auditoría: 365 días y 10 000 filas, aplicados por la función que escribe; la lectura une el correo solo si la cuenta existe | INV-059, REQ-N-029 |
| 14 | Lista de 25 (sin parámetro de tamaño), `pagina` 1 a 400; `q` de 1 a 60 caracteres, texto literal con comodines escapados, sin filtro por estado | INV-060, REQ-N-028 |
| 15 | Límites 60/min y 20 acciones/min por Dueño, **en memoria por instancia** (se suma a la excepción de INV-013/BL-040); plazo de 5 s y 503 sin encolar con el ejecutor acotado del estado de autenticación | INV-060, ADR-012 (9) |
| 16 | Conteos por función SQL de solo lectura que arma el `jsonb` con claves explícitas; **sin cuentas de dinero** hasta que exista esa tabla (CHG-019); `ultimo_acceso` = último inicio de sesión (no actividad) | INV-055, INV-062, ADR-012 (4, 10) |

## 4. Preguntas abiertas reales (ninguna bloquea la spec; llevan respuesta por defecto)
| # | Pregunta | Por defecto (provisional) | Respuesta |
|---|---|---|---|
| P1 | El riesgo aceptado de ADR-008 (si el dueño borra su cuenta y otra persona registra y verifica ese correo, obtiene el acceso) ahora incluiría **borrar cuentas de todos**. ¿Se acepta, o se exige además un id de usuario fijo (`OWNER_USER_ID`) o reautenticación para eliminar? | Aceptar; mitigación opcional en BL-036 | **Decidida por el dueño (2026-11-25): reautenticación.** Eliminar exige además `contrasena_dueno` (INV-058, ADR-012 punto 12); el id fijo sigue en BL-036 |
| P2 | ¿Debe llegar un correo (Brevo) a la persona suspendida o eliminada, o una nota con el motivo? | No (fuera de alcance; evita datos personales y texto libre) | **Decidida por el dueño (2026-11-25): no avisar.** También aceptó el 403 «Contacta al administrador» del login de una suspendida y el `ultimo_acceso` en segundo plano |

## 5. Spec afectada (fuente única de pruebas: INV-053 a INV-062 y BDD-ADMIN-USUARIOS; aquí solo el índice)
**Aprobación de la spec:** aprobada por el dueño el 2026-11-25 con las correcciones del informe del validador (§7).

| Documento | Cambio |
|---|---|
| `REQUIREMENTS.md` | **REQ-F-021** (CA-1 a CA-11), actor Dueño, alcance, REQ-N-027 a N-031, preguntas abiertas 15 y 16 |
| `05-INVARIANTS.md` | **INV-053 a INV-062** nuevas; ampliadas INV-013 (excepción del limitador), INV-016, INV-017 (suspendida), INV-012 (nota) |
| `CONTRACTS/CT-013-admin-usuarios.md` | Nuevo: 7 rutas, esquemas, 404/405/409/422/429/503, cabeceras, funciones SQL. `CT-001`: 403 del login |
| `ADR/ADR-012-...md` · `USE-CASES/UC-017-...md` · `BDD/BDD-ADMIN-USUARIOS.feature` | Nuevos |
| `NFR/NFR.md` · `01-GLOSSARY.md` · `02-ENTITIES.md` · `04-STATES.md` | REQ-N-027 a N-031; términos (Administrador/Dueño, Suspender, Cerrar sesiones, Panel de usuarios, Registro de acciones, Último acceso); entidades y estado `suspendida` |
| `TRACEABILITY.md` · `work/BACKLOG.md` | REQ-F-021, INV-053 a INV-062 · BL-042 |

**Pruebas (índice; los nombres exactos están en INV y BDD):**
| Archivo | Cubre |
|---|---|
| `backend/tests/test_admin_usuarios.py` | INV-053 (15), INV-054 (6), INV-055 (7), INV-058 (19),  INV-059 (7 de API), INV-060 (13) y REQ-N-027/N-028 |
| `backend/tests/test_admin_suspension.py` | INV-056 (14), INV-057 (4), INV-061 (8) |
| `backend/sql/pruebas/11_comprobar_admin_usuarios.sql` (+ `probar.sh`) | INV-062 y la atomicidad real contra PostgreSQL: RLS y privilegios, idempotencia, funciones de solo lectura, `jsonb` sin claves sensibles, suspensiones simultáneas, cierres simultáneos, baja con datos en todas las tablas, auditoría atómica/retención/tope, 20 `registrar_acceso` simultáneos, 1 000 usuarios < 2 s |
| `frontend/tests/admin-usuarios.test.mjs` | Helpers puros de `fe/lib/admin-usuarios.ts`: `etiquetaEstado`, `correoCoincide` (mayúsculas y espacios), `busquedaValida` (1 a 60, sin control), `paginasTotales`, `mensajeDeError` (404/409/422/429/503) |

**Migración planificada** `backend/sql/2026-11-25_admin_usuarios.sql` (idempotente, pegable completa en el SQL Editor, solo `if not exists` / `create or replace`):
1. `alter table public.users add column if not exists suspendida boolean not null default false` y `... ultimo_acceso timestamptz` (ninguna fila existente cambia; 5 usuarios hoy).
2. `auditoria_admin(id bigint generated always as identity, creado_en timestamptz not null default now(), accion text not null check (accion in ('suspender','reactivar','cerrar_sesiones','eliminar')), usuario_id uuid not null)` **sin llave foránea**; índice `(creado_en desc, id desc)`; `enable row level security` sin políticas; `revoke all ... from anon, authenticated`.
3. Funciones `SECURITY INVOKER`, `search_path = public`, `revoke ... from public, anon, authenticated` y `grant execute ... to service_role` (con `if exists (select from pg_roles ...)` como `2026-11-24_monitor_tamano_bd.sql`): `admin_listar_usuarios`, `admin_detalle_usuario`, `admin_auditoria` (`STABLE`, solo lectura, `jsonb` con claves explícitas, `limite` acotado a 25 y desplazamiento a 9 975), `admin_suspender_usuario`, `admin_reactivar_usuario`, `admin_cerrar_sesiones_usuario`, `admin_eliminar_usuario` (cada una: `select ... for update`, cambio de estado y `admin_registrar_auditoria` en la misma transacción; devuelven `ok`, `no_existe`, `ya`, `pendiente`, `no_suspendida` o `correo_distinto`), `admin_registrar_auditoria` (inserta y aplica 365 días y 10 000 filas), `registrar_acceso` (un `update ... where ultimo_acceso is null or ultimo_acceso < now() - interval '1 hour'` que devuelve si escribió).
4. Comprobación final al pie (`select`), igual que las migraciones anteriores. La del número 11 de pruebas se suma a `probar.sh`.

**Checklist previo del generador (aplicado a esta spec):** plazo real en cada llamada (cliente de 4 s + presupuesto de 5 s y `registrar_acceso` de 2 s) · trabajo fuera del event loop con ejecutor acotado y 503 sin encolar (`auth_estado.ejecutar`) · estado de seguridad atómico en la base (funciones `admin_*`) · sin datos personales ni excepciones completas en logs (INV-055) · retención y tope de la auditoría (REQ-N-029) · cada prueba nombrada existe con ese nombre (INV y BDD) · trazabilidad y notas de despliegue al día · pruebas SQL contra PostgreSQL real · **toda consulta nueva se comprueba contra el esquema real** (`users` con `id, email, hashed_password, full_name, is_active, created_at, updated_at, currency, session_version`; `categorias`, `transacciones`, `presupuestos`, `metas`, `recurrentes`, `whatsapp_enlaces` con `usuario_id`; confirmar columnas con el MCP de Supabase o `information_schema` antes de escribir las funciones).

## 6. Plan de tareas (cada una ~10 min y un solo propósito; T2 y T4 pueden ir en paralelo cuando T1 esté hecha)
| Tarea | Alcance | Depende de | Estado |
|---|---|---|---|
| T1 | SQL: `2026-11-25_admin_usuarios.sql` + `pruebas/11_comprobar_admin_usuarios.sql` + línea en `probar.sh` (INV-062 y la atomicidad de INV-056/057/058/059/061) | spec aprobada | **hecha** (2026-11-25; ver §7) |
| T2 | Backend: `models/admin_usuarios.py` (RPC con `auth_estado.ejecutar`), `schemas/admin_usuarios.py`, `api/routes/admin_usuarios.py` (despachador ASGI, `_confirmar_dueno`, límites, lista blanca), registro en `main.py` y `tests/test_admin_usuarios.py` | T1 | **hecha** (2026-11-25) |
| T3 | Login/sesión: `suspendida` en `UserDB._map_user`/`get_session_version`, 401 en `usuario_de_sesion`, 403 en `login` y `verify-email`, `registrar_acceso` best-effort y `tests/test_admin_suspension.py` | T1 | **hecha** (2026-11-25) |
| T4 | Frontend: `app/dashboard/usuarios/page.tsx` (lista, búsqueda, detalle, diálogos con `useDialog`, confirmación escribiendo el correo, pestaña «Registro», `ErrorState`, «no encontrada» ante 404), enlace «Usuarios» por `es_dueno`, `lib/usuarios.ts` y `frontend/tests/usuarios.test.mjs` | T2 (contrato CT-013) | **hecha** (2026-11-25; ver §7) |
| T5 | Validación (suite una vez, `pip-audit`, SQL contra PostgreSQL real, scripts de abuso: 404 byte a byte, 422 a no-Dueño, inyección en `q`) y revisión independiente **en paralelo**; trazabilidad y notas de despliegue; aprobación del dueño | T1-T4 | pendiente |

## 7. Registro de ejecución
| Fecha | Agente | Acción | Resultado |
|---|---|---|---|
| 2026-11-25 | coordinador | Pedido y decisiones registrados | CHG creado |
| 2026-11-25 | generador | Redacción de la spec (solo especificación, sin código ni commit) | REQ-F-021, INV-053 a INV-062, CT-013, ADR-012, UC-017, BDD-ADMIN-USUARIOS, REQ-N-027 a N-031, glosario, entidades, estados, CT-001, TRACEABILITY, BL-042; decisiones 8 a 16 y preguntas P1 y P2 para el dueño |
| 2026-11-25 | generador | Parte A (spec): contraseña del Dueño para eliminar, `ultimo_acceso` en segundo plano, 404 de subruta inexistente sin `no-store`, cuerpo de DELETE con tope real de 2 KB (413/422) y borrado > 5 s, zona horaria de `created_at`, `confirmar_correo` 3 a 255, tope de auditoría con try-lock, banco de pruebas de REQ-N-027, `whatsapp_mensajes`/`whatsapp_registros` en INV-058, P1/P2 registradas | REQ-F-021, INV-053/056/058/059/061/062, CT-013, ADR-012 (punto 12), UC-017, BDD, NFR |
| 2026-11-25 | generador | T1: migración `backend/sql/2026-11-25_admin_usuarios.sql`, `pruebas/11_comprobar_admin_usuarios.sql` y bloque de concurrencia en `probar.sh` | ver informe de la tarea |
| 2026-11-25 | generador | T4: `app/dashboard/usuarios/page.tsx`, enlace «Usuarios» en `layout.tsx` (solo `es_dueno`), `lib/usuarios.ts`, `tests/usuarios.test.mjs`; verificado con Playwright (respuestas simuladas, dueño y no dueño). El filtro por estado es solo de la página cargada (CT-013 no filtra por estado) y la lista solo trae `transacciones` (WhatsApp y demás conteos, en el detalle) | LISTO_PARA_VALIDAR |
| 2026-11-25 | generador | T2+T3 (backend): panel `/admin/*` con despachador ASGI, modelo RPC con modo demo, esquemas, `suspendida` en sesión/login/verify-email, `ultimo_acceso` en segundo plano; `test_admin_usuarios.py` y `test_admin_suspension.py` (93 nombres de INV/BDD presentes); ajustados 3 conteos de llamadas a la BD en `test_auth_persistente.py` (+1 `registrar_acceso`) | ver informe de la tarea |

## 8. Cierre
- **Aprobación humana final:** pendiente

## Cierre de la revisión (2026-11-25)
- Validador PASA (888 pruebas, pip-audit, pyflakes, frontend 81/81, SQL contra PostgreSQL real, barrido de abuso 11/11) y revisor APROBADO, sin bloqueantes.
- Columnas del SQL verificadas contra la base real de Supabase (users, whatsapp_enlaces, whatsapp_mensajes, whatsapp_registros, categorias, transacciones, presupuestos, metas, recurrentes).
- Menores aceptados: redacción de INV-054 corregida («antes de cualquier escritura o auditoría»); ~~`registrar_acceso` comparte el ejecutor de 8 hilos con el login~~ (**cerrado** 2026-11-25: semáforo `BoundedSemaphore(2)` y ejecutor propio de 2 hilos, omite sin hueco; INV-061, ADR-012 punto 10, 3 pruebas nuevas); tiempos de un no-Dueño con sesión válida (igual que el Monitor); paso 07 de `probar.sh` muy lento en un entorno de pruebas (preexistente, no es de CHG-023).
- Despliegue: ejecutar `backend/sql/2026-11-25_admin_usuarios.sql` COMPLETO en Supabase ANTES del push a `main` (sin la migración, `get_session_version` falla y todas las sesiones dan 503). Sin variables nuevas.
