# UC-017 — Administrar usuarios (solo el Dueño)

- **REQ:** F-021 · **Contrato:** CT-013 (y CT-001 `login` 403) · **Invariantes:** INV-053 a INV-062 (y INV-016, INV-017, INV-031, INV-040) · **CHG:** CHG-023 · **ADR:** ADR-012 · **Estado:** provisional
- **Actor:** Dueño (sesión con el correo de `OWNER_EMAIL`). Un único administrador.

## Precondiciones
`OWNER_EMAIL` configurada, migración `2026-11-25_admin_usuarios.sql` ejecutada, el Dueño con sesión activa.

## Flujo principal
1. El Dueño ve el enlace «Usuarios» (solo si `es_dueno` es `true`, CT-002) y abre `/dashboard/usuarios`.
2. La pantalla pide `GET /api/v1/admin/usuarios` (25 por página) y muestra correo, nombre, estado, moneda, fecha de registro, último
   inicio de sesión y cuántas transacciones tiene; puede **buscar** por correo o nombre.
3. Al abrir un usuario ve su detalle con el uso agregado (cantidades de transacciones, categorías, presupuestos, metas, recurrentes y si
   tiene WhatsApp conectado; **nunca** montos, descripciones ni categorías).
4. **Suspender:** confirma en un diálogo; la persona pierde el acceso al instante (sesiones abiertas incluidas) y no puede iniciar sesión.
   **Reactivar:** confirma; la persona puede iniciar sesión de nuevo (con una sesión nueva).
5. **Cerrar sesiones:** confirma; todas sus sesiones dejan de valer y debe iniciar sesión de nuevo (WhatsApp se desconecta).
6. **Eliminar:** el diálogo exige **escribir el correo** de la cuenta; se borran la cuenta y todos sus datos (irreversible).
7. Cada acción queda en el registro de acciones, que el Dueño ve en la pestaña «Registro» (`GET /admin/auditoria`).

## Flujos alternos y excepciones
- No-Dueño, sin sesión, sesión inválida, BD caída al autorizar o `OWNER_EMAIL` sin configurar → 404 fail-closed (INV-053); la interfaz oculta el
  enlace y, por la dirección, la página muestra «no encontrada».
- Sobre su propia cuenta el Dueño no puede suspender, eliminar ni cerrar sesiones (409; su fila no ofrece acciones).
- Suspender a una cuenta pendiente o ya suspendida, o reactivar una que no lo está → 409. Usuario que ya no existe → 404 «Usuario no encontrado».
- Correo de confirmación que no coincide → 422 y no se borra nada.
- Más de 60 peticiones por minuto (o 20 acciones) → 429. BD caída o lenta (> 5 s) → 503 con aviso de comprobar el estado antes de reintentar.
- La persona suspendida: con contraseña correcta recibe 403 con un mensaje genérico; con incorrecta, 401 como siempre; su sesión abierta recibe 401.
- Falla la limpieza de intentos y códigos tras eliminar → la baja **no** se revierte; se avisa sin datos (INV-058).
- Falla el registro del último acceso al iniciar sesión → el inicio de sesión continúa (INV-061).

## Postcondiciones
Cada acción exitosa dejó **un** registro (`suspender`, `reactivar`, `cerrar_sesiones`, `eliminar`) con el id del usuario afectado y la fecha, sin datos personales
(INV-059); una acción rechazada o fallida no deja registro ni cambia nada.
