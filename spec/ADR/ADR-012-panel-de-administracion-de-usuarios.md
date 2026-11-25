# ADR-012 — Panel de administración de usuarios solo para el Dueño

- **Estado:** **aprobada por el dueño** el 2026-11-25 con correcciones (reautenticación para eliminar, punto 12; `ultimo_acceso` en segundo plano, punto 10; P1 y P2 decididas). Las alternativas marcadas «provisional» siguen siendo decisiones por defecto del coordinador que el dueño puede cambiar.
- **Fecha:** 2026-11-25 · **Decide:** dueño del proyecto (las alternativas marcadas «provisional» las fijó el coordinador y el dueño puede cambiarlas)

## Contexto
El dueño quiere «control de todos los que se registran» (CHG-023 §1): ver y buscar usuarios, suspender y reactivar, cerrar sus
sesiones, eliminar la cuenta con todos sus datos y dejar un registro de lo que hace. Hoy no hay roles de administrador
(REQUIREMENTS §3); el Monitor (ADR-008) ya definió al actor **Dueño** (correo de `OWNER_EMAIL`, fail-closed). Este panel **amplía**
el privilegio del Dueño de «solo lectura» a «acciones sobre otras cuentas», por eso es riesgo alto.

## Decisiones
1. **Mismo actor y misma barrera que el Monitor (provisional, por defecto seguro).** Solo el Dueño (`es_correo_dueno`, INV-031);
   todo lo demás, incluido cualquier fallo al autorizar, responde 404 idéntico al de una ruta inexistente (INV-053). No hay un
   rol nuevo ni una tabla de administradores: un único administrador, el de `OWNER_EMAIL`. La ruta `/admin/*` se atiende con un
   despachador ASGI propio (como `_RutaCualquierMetodo` del Monitor) que **autoriza antes de validar nada**: si FastAPI validara
   parámetros o cuerpo antes, un no-Dueño recibiría 422 y se sabría que la ruta existe.
2. **Suspensión con columna nueva `users.suspendida` (decisión del dueño en el pedido; el nombre es provisional).** No se reutiliza
   `is_active`: `delete_unverified_expired` borra las filas con `is_active = false` creadas hace más de 1 hora, y una persona
   suspendida (activa) con `is_active = false` desaparecería con sus datos; además `reset-password` pone `is_active = true` y
   reactivaría sola a la persona. `suspendida` solo la cambia el Dueño desde el panel. Estados visibles: `activa`, `pendiente`,
   `suspendida` (la suspendida solo existe sobre una cuenta activa: suspender una pendiente → 409).
3. **Efecto inmediato de la suspensión (INV-056).** La acción sube `session_version` (INV-016) **y** marca `suspendida` en la misma
   función SQL; además `usuario_de_sesion` trata `suspendida` como cuenta no válida (401, igual que INV-017) leyendo la columna
   en la **misma** consulta que ya hace (`get_session_version`), sin consulta extra. El login con contraseña correcta de una
   persona suspendida responde 403 con un mensaje genérico y **no** emite sesión ni código; con contraseña incorrecta responde el
   401 de siempre (no se revela el estado a quien no conoce la contraseña). `verify-email` tampoco emite sesión a una suspendida.
   La suspensión también borra el enlace de WhatsApp (como INV-016 al cambiar la contraseña): sin esto, el webhook seguiría
   registrando transacciones a nombre de la cuenta suspendida.
4. **Conteos agregados con funciones SQL de solo lectura (provisional).** Las consultas del panel viven en funciones
   `admin_*` que devuelven `jsonb` armado con **claves explícitas** (nunca `to_jsonb(users)` ni `select *`): el hash de la
   contraseña no sale de la base, y los conteos (`count(*)` sobre categorías, transacciones, presupuestos, metas, recurrentes y
   `exists` de WhatsApp) no seleccionan montos, descripciones ni nombres de categorías. Una consulta por petición (lista paginada
   con sus conteos; los conteos se calculan solo para las 25 filas de la página). `EXECUTE` solo para `service_role`; `REVOKE` a
   `anon`, `authenticated` y `public`. `users.created_at` es `timestamp` **sin zona** (guarda UTC): la función lo interpreta como UTC y devuelve ISO con `Z`. Las cuentas de dinero (CHG-019) **no** se cuentan mientras esa tabla no exista; se añade
   en la migración de CHG-019 o en una posterior (no se consulta una tabla inexistente).
5. **Acciones atómicas con su registro de auditoría.** Suspender, reactivar, cerrar sesiones y eliminar son **cada una una función
   SQL** que, en una sola transacción y con la fila del usuario bloqueada (`FOR UPDATE`), cambia el estado y escribe el registro de
   `auditoria_admin`: no puede existir una acción sin registro ni un registro sin acción, y dos acciones simultáneas sobre el mismo
   usuario se serializan (la segunda ve el estado nuevo y responde 409). Estado de seguridad en la base y atómico (lista previa del
   generador, punto 3).
6. **Baja reutilizada, con orden seguro (provisional).** Eliminar reutiliza lo de REQ-F-013: el borrado de `users` con la cascada
   de llaves foráneas (categorías, transacciones, presupuestos, metas, recurrentes, enlace de WhatsApp y, cuando existan, cuentas de
   dinero y transferencias) y, **después**, `auth_estado.borrar_de_cuenta(correo)` (intentos y códigos por huella; si falla, la baja
   no se revierte y solo hay un aviso sin datos, INV-040). La diferencia deliberada: el `DELETE` de `users` y la auditoría van en la
   función `admin_eliminar_usuario` (atómica), no en `UserDB.delete_by_id`, que oculta los errores y devolvería «no existe» ante un
   fallo. Orden: (a) leer correo y comprobar confirmación y autoprotección, y (a2) contraseña del Dueño (punto 12); (b) función atómica (auditoría
   + borrado); (c) limpieza de autenticación best-effort. Si (b) falla no queda nada a medias; si (c) falla solo quedan huellas que se purgan a
   los 30 días. Si (b) pasa de 5 s el cliente recibe 503 pero el borrado puede terminar: la función es atómica (auditoría y borrado juntos o
   ninguno), así que nunca queda la auditoría a medias; (c) se omite y reintentar responde 404 si ya se borró.
7. **Auditoría sin datos personales (decisión del dueño: «registro de acciones»; forma provisional).** `auditoria_admin(id, creado_en,
   accion, usuario_id)`: **sin llave foránea** (sobrevive a la baja), sin correo, nombre, IP ni texto libre, y sin id del
   administrador (hay uno solo, definido por `OWNER_EMAIL`). La lectura (`GET /admin/auditoria`) añade el correo **solo si la
   cuenta aún existe** (unión al leer, nada se copia al registro). Retención y tope (lista previa, punto 5): 365 días y 10 000
   filas; se aplican dentro de la misma función que escribe, sin tarea programada, **solo al superarlos** y con `pg_try_advisory_xact_lock` (si otra sesión ya limpia, no espera ni recorta). No hay rutas para editar ni borrar registros.
8. **Autoprotección (INV-054).** Ninguna acción de escritura sobre la propia cuenta del Dueño (suspender, eliminar, cerrar sus
   sesiones) → 409; se comprueba por id de la sesión **y** por correo del objetivo. El id de la cuenta del Dueño no aparece en las
   respuestas (`id: null`, `es_dueno: true`, sin acciones). Para eliminar la cuenta propia queda `DELETE /users/me` (Perfil).
9. **Límites (provisional).** 60 peticiones/min por Dueño en total y **20/min** para POST/DELETE; cuentan 200, 405 y 429; solo tras
   confirmar al Dueño. El limitador es **en memoria por instancia** (`SlidingWindow`, como el del Monitor): se declara como
   **excepción explícita de INV-013 junto a BL-040**, porque protege contra abuso de una sesión ya autorizada y de carga, no es la
   barrera de seguridad (esa son la autorización fail-closed, la confirmación por correo y las funciones atómicas).
10. **Último acceso (provisional).** `users.ultimo_acceso` lo escribe la función `registrar_acceso(id)` con el reloj de la BD y una
    sola sentencia condicional (como mucho una vez por hora por usuario: si ya se escribió hace menos de 1 h no toca la fila).
    **Límite propio:** la escritura corre en un ejecutor propio de 2 hilos (`auth-acceso`) con un `BoundedSemaphore(2)` adquirido sin
    bloquear; sin hueco se omite el guardado de ese acceso (mejor esfuerzo, aviso sin datos limitado) y el hueco se libera al terminar el
    hilo. Así no compite con los 8 hilos de `auth_estado` (login, registro, restablecimiento). Se reutiliza el cliente dedicado de
    `auth_estado` (plazo de 4 s, sin reintentos; es seguro entre hilos) y se impone el plazo propio de 2 s; no se duplica el cliente.
    Se invoca al emitir una sesión (login y `verify-email`) como **mejor esfuerzo y en segundo plano tras responder** (`BackgroundTasks`:
    la respuesta sale antes de escribir; decisión del dueño), con plazo propio de 2 s y fuera del event loop; su fallo, lentitud o respuesta
    rara no afecta la respuesta y solo deja un aviso sin datos. Significa «último inicio de sesión»: la sesión dura 7 días, así que
    no es actividad en la app (se rotula así en la interfaz).
12. **Reautenticación para eliminar (decisión del dueño; resuelve P1).** `DELETE /admin/usuarios/{id}` exige además `contrasena_dueno` en el cuerpo
    (tope real de 2 KB, 413/422): se comprueba con bcrypt en `auth_estado.ejecutar_bcrypt` y con el mismo bloqueo por intentos que el login del Dueño
    (`login_reservar`/`login_resolver` con la huella del correo del Dueño; incorrecta → 403 genérico y cuenta como fallo; 5 fallos bloquean, 429 como
    el login). La contraseña no llega a logs ni auditoría. Suspender, reactivar y cerrar sesiones no la piden (son reversibles). Así, quien registre
    el correo del Dueño tras su baja podría entrar al panel (ADR-008) pero **no borrar cuentas** sin conocer la contraseña de esa cuenta.
13. **Sin cambios de costo ni de dependencias.** Sin librerías nuevas, sin variables de entorno nuevas (reutiliza `OWNER_EMAIL`).

## Alternativas descartadas
| Opción | Por qué no |
|---|---|
| Usar `is_active = false` para suspender | La limpieza de cuentas sin verificar la borraría; `reset-password` la reactivaría |
| Comprobar la suspensión solo en el login | Las sesiones abiertas (7 días) seguirían valiendo; lo exige INV-016 |
| Rol «admin» en la tabla `users` o varios administradores | Amplía privilegios más de lo pedido; un solo Dueño basta |
| Auditoría con correo del afectado | Dato personal que sobreviviría a la baja; el id basta |
| Auditoría con llave foránea a `users` | La baja la borraría (`CASCADE`) o la impediría (`RESTRICT`) |
| Hacer en Python «leer, cambiar, auditar» | No es atómico; un fallo a medias deja acciones sin registro |
| Listar con `select *` y filtrar en Python | Un descuido filtraría `hashed_password`; la función entrega solo claves explícitas |
| Registrar el último acceso en cada petición | Una escritura por petición; el pedido es «al iniciar sesión» |

## Consecuencias
- **Migración** `backend/sql/2026-11-25_admin_usuarios.sql` (idempotente, pegable completa en el SQL Editor) **antes** de desplegar el
  backend: sin la columna `suspendida`, `get_session_version` fallaría y todas las sesiones responderían 503. Pruebas en
  `backend/sql/pruebas/11_comprobar_admin_usuarios.sql` y en el CI «Migraciones SQL» (`probar.sh`).
- Sin variables nuevas en Railway (`OWNER_EMAIL` ya existe y sigue siendo obligatoria: sin ella el panel responde 404 a todos).
- **P1 resuelta por el dueño:** el acceso se concede por correo verificado (ADR-008); si el Dueño elimina su cuenta y otra persona registra y
  verifica ese correo, obtendría el panel. La reautenticación del punto 12 impide que borre cuentas; sigue abierto en BL-036 solo el id fijo.
- **P2 resuelta por el dueño:** no se avisa por correo a la persona suspendida o eliminada. **Aceptados por el dueño:** el 403 «Contacta al
  administrador» en el login de una suspendida (revela que la cuenta existe solo a quien conoce la contraseña) y `ultimo_acceso` en segundo plano.
- El camino 404 no tiene límite propio (igual que ADR-008).
- Fuera de alcance: correos de aviso a la persona suspendida o eliminada, motivo de suspensión, editar datos del usuario, ver sus
  transacciones, reiniciar contraseñas, varios administradores, exportar la lista.
