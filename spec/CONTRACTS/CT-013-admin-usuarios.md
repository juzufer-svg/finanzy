# CT-013 — Administración de usuarios del Dueño `/api/v1/admin`

- **Versión:** v1 (CHG-023, **provisional** hasta aprobación del dueño) · **UC:** UC-017 · **REQ:** F-021 · **ADR:** ADR-012 · **INV:** INV-053 a INV-062
- Solo el **Dueño** (glosario; correo de `OWNER_EMAIL`). Únicos métodos: **GET, POST y DELETE**. Los errores comunes 401/503 de sesión
  (CT-002) **no** se usan aquí: ver «Autorización» y «Errores».
- «Administrador» en este documento = el Dueño. No existe otro rol.

## Endpoints
| Endpoint | Entrada | Respuesta |
|---|---|---|
| `GET /admin/usuarios` | `q` (opcional, búsqueda) y `pagina` (opcional, por defecto 1) | 200 lista paginada (abajo) |
| `GET /admin/usuarios/{id}` | `id` UUID | 200 detalle |
| `POST /admin/usuarios/{id}/suspender` | sin cuerpo | 200 detalle con `estado: "suspendida"` |
| `POST /admin/usuarios/{id}/reactivar` | sin cuerpo | 200 detalle con `estado: "activa"` |
| `POST /admin/usuarios/{id}/cerrar-sesiones` | sin cuerpo | 200 detalle (mismo `estado`) |
| `DELETE /admin/usuarios/{id}` | cuerpo JSON `{ "confirmar_correo": "<correo del usuario>" }` | 204 sin cuerpo |
| `GET /admin/auditoria` | `pagina` (opcional) | 200 registros |

No existe ninguna otra ruta, ni `PUT`/`PATCH`, ni rutas para editar o borrar registros de auditoría, ni para ver transacciones,
categorías, presupuestos o metas de otro usuario.

## Autorización (INV-053) — igual que CT-010, aplicada a **todo** `/admin/*`
En cada petición, en este orden y **fail-closed**:
1. `OWNER_EMAIL` vacío o ausente → 404 (ni se mira la sesión).
2. Sesión verificada (JWT, cuenta activa **y no suspendida**, versión de sesión). Cualquier fallo (ausente, inválida, BD caída) → 404.
3. Correo de la sesión vs `OWNER_EMAIL` con `strip().lower()` y `hmac.compare_digest` (`es_correo_dueno`) → distinto → 404.
4. **Solo ahora** (es el Dueño): límite de frecuencia (429) → método (405) → validación de parámetros/cuerpo (422) → autoprotección (409)
   → existencia (404 «Usuario no encontrado») → estado (409) → acción → 503 si la BD falla o excede 5 s.

Reglas por método y ruta (registrada para **cualquier** método, `redirect_slashes` desactivado; despachador propio, la validación de
FastAPI **no** corre antes de autorizar):
- **No-Dueño** (sin sesión, sesión inválida o cualquier usuario) con **cualquier** método sobre **cualquier** ruta bajo `/admin/*`
  (existente o no, con parámetros válidos o inválidos, con o sin cuerpo) → **404** byte a byte idéntico (cuerpo `{"detail":"Not Found"}`
  y cabeceras, salvo `Date`) al de `GET /api/v1/no-existe`, **sin** `Cache-Control: no-store`. Nunca 401/403/405/422/429/503.
- **Dueño** con un método no permitido sobre una ruta existente (p. ej. `PUT`, `PATCH`, `HEAD`, `GET` sobre `.../suspender`) →
  **405** con `Allow` (los métodos de esa ruta) y `no-store`; cuenta para el límite.
- **Dueño** sobre una ruta inexistente bajo `/admin/*` (incluida la barra final) → 404 normal de la API, sin límite.
- El segmento `{id}` que no es un UUID → 404 para el no-Dueño y **422** para el Dueño (después de confirmarlo).

## Listas: paginación y búsqueda (INV-060)
- Tamaño de página **fijo de 25** (no hay parámetro `por_pagina`). `pagina`: entero 1 a 400 (tope de 10 000 filas alcanzables); fuera
  de rango, no entero o repetido → 422.
- `q` (solo `GET /admin/usuarios`): se recorta; 1 a 60 caracteres, sin caracteres de control; se busca como **texto literal** (`%`, `_` y `\`
  se escapan) con `ILIKE` sobre correo **o** nombre, sin distinguir mayúsculas (tampoco tildes: no se normalizan). Vacío o ausente = sin
  filtro. Inválido → 422. Va como parámetro de una función SQL, nunca concatenado.
- Orden de usuarios: `created_at` descendente, luego `id`. Orden de auditoría: `creado_en` descendente, luego `id`.

## Respuestas (lista blanca; INV-055)
**`GET /admin/usuarios` → 200**
```json
{
  "generado_en": "2026-11-25T15:00:00Z",
  "pagina": 1, "por_pagina": 25, "total": 1, "total_paginas": 1,
  "usuarios": [
    { "id": "uuid", "correo": "ana@ejemplo.com", "nombre": "Ana Pérez", "estado": "activa",
      "moneda": "COP", "registrado_en": "2026-11-20T10:00:00Z", "ultimo_acceso": "2026-11-25T09:00:00Z",
      "es_dueno": false, "uso": { "transacciones": 42 } }
  ]
}
```
**`GET /admin/usuarios/{id}` y las respuestas de las acciones → 200**: el mismo objeto de usuario con
`"uso": { "transacciones", "categorias", "presupuestos", "metas", "recurrentes": <int>, "whatsapp_conectado": <bool> }`.

**`GET /admin/auditoria` → 200**
```json
{ "generado_en": "...", "pagina": 1, "por_pagina": 25, "total": 1, "total_paginas": 1,
  "registros": [ { "id": 7, "fecha": "2026-11-25T15:01:00Z", "accion": "suspender",
                   "usuario_id": "uuid", "usuario_correo": "ana@ejemplo.com" } ] }
```
- `estado` ∈ `activa` | `pendiente` | `suspendida` (suspendida si `suspendida`; si no, `activa` si `is_active`, si no `pendiente`).
- `accion` ∈ `suspender` | `reactivar` | `cerrar_sesiones` | `eliminar`. `usuario_correo` es `null` si la cuenta ya no existe.
- Instantes en UTC ISO-8601 con `Z` (`YYYY-MM-DDTHH:MM:SSZ`); `ultimo_acceso` es `null` si nunca inició sesión desde CHG-023
  (significa «último inicio de sesión», no actividad). `total_paginas` ≥ 1.
- **Nunca** aparecen: `hashed_password`, `session_version`, `is_active` ni `suspendida` como booleanos sueltos, tokens, IP, teléfono
  de WhatsApp, ni montos, descripciones, nombres de categorías, metas o cuentas de dinero: solo los conteos y el booleano
  `whatsapp_conectado` de arriba. El `id` de la cuenta del Dueño se devuelve como `null` (con `es_dueno: true`); en la auditoría nunca
  aparece porque no se pueden hacer acciones sobre ella.
- Clave desconocida o tipo distinto en lo que entrega la BD → se descarta (misma regla que INV-032) y, si falta lo esencial, 503.

## Acciones (INV-056 a INV-059)
| Acción | Precondición | Efectos (una sola transacción, con la fila bloqueada) | Si no se cumple |
|---|---|---|---|
| `suspender` | cuenta activa, no suspendida, no la del Dueño | `suspendida = true`, `session_version + 1`, borra el enlace de WhatsApp, registra `suspender` | 409 (propia cuenta / pendiente / ya suspendida) |
| `reactivar` | cuenta suspendida | `suspendida = false`, registra `reactivar` (las sesiones viejas **no** reviven: su `sv` ya no coincide) | 409 (no suspendida) |
| `cerrar-sesiones` | no la del Dueño | `session_version + 1`, borra el enlace de WhatsApp, registra `cerrar_sesiones` | 409 (propia cuenta) |
| `eliminar` | `confirmar_correo` = correo del usuario (`strip().lower()`, `hmac.compare_digest`), no la del Dueño | registra `eliminar` y borra `users` (cascada); luego `auth_borrar_de_cuenta(correo)` (best-effort, INV-058) | 422 (confirmación), 409 (propia cuenta) |
Sin cuerpo en `POST` (si llega uno se ignora, máximo 2 KB). `DELETE`: el cuerpo es un objeto con **solo** `confirmar_correo` (texto de 3 a 254 caracteres); falta, clave extra, tipo distinto o más de 2 KB → 422.

## Errores
| Código | Cuándo | `detail` |
|---|---|---|
| 404 | No-Dueño con cualquier método y ruta (sin pistas, idéntico a una ruta inexistente); además, **solo el Dueño**: usuario inexistente | «Not Found» (no-Dueño) · «Usuario no encontrado» (Dueño) |
| 405 | Solo el Dueño, método no permitido sobre una ruta existente (`Allow`) | «Método no permitido» |
| 409 | Solo el Dueño: acción sobre su propia cuenta; suspender una cuenta pendiente o ya suspendida; reactivar una que no lo está | «No puedes hacerlo sobre tu propia cuenta» · «La cuenta aún no está verificada» · «La cuenta ya está suspendida» · «La cuenta no está suspendida» |
| 422 | Solo el Dueño: `id`, `pagina`, `q` o cuerpo inválidos; correo de confirmación que no coincide | «El correo escrito no coincide con el de la cuenta» y mensajes de validación |
| 429 | Solo el Dueño: más de 60 peticiones/min, o más de 20 `POST`/`DELETE`/min (INV-060) | «Demasiadas consultas. Intenta de nuevo en un minuto.» |
| 503 | Solo el Dueño: la BD falla, no hay hilo libre (sin encolar) o excede 5 s | «No se pudo completar la operación. Revisa el estado del usuario antes de reintentar.» |
Un no-Dueño que «supere» un límite recibe 404, nunca 429. El camino 404 no tiene límite propio (riesgo aceptado, ADR-008).

## Cabeceras
- `Cache-Control: no-store` en **todas** las respuestas al Dueño confirmado (200, 204, 405, 409, 422, 429, 503 y el 404 «Usuario no encontrado»).
  El 404 del no-Dueño y el de rutas inexistentes **no** lo llevan (idéntico al 404 normal de la API).
- Sin `Set-Cookie`. El proxy de Next.js reenvía `DELETE` con cuerpo y exige el encabezado CSRF (ADR-005); sin cambios en el proxy.

## Cambios en otros contratos (CHG-023)
- **CT-001 `login`:** nuevo **403** «No fue posible iniciar sesión con esta cuenta. Contacta al administrador.» **solo** cuando la contraseña es
  correcta y la cuenta está suspendida (sin token ni código; no cuenta como fallo y reinicia la serie de fallos como cualquier acierto).
  Con contraseña incorrecta sigue el 401 «Credenciales inválidas». `verify-email` responde el mismo 403 a una suspendida. `reset-password`
  no reactiva. Mensaje y código **provisionales**.
- **CT-002 (errores comunes):** una sesión de cuenta suspendida o con la versión de sesión superada recibe el 401 «Tu sesión ya no es válida…» (INV-016, INV-017, INV-056, INV-057).
- `GET /users/me` y `es_dueno` no cambian; la interfaz usa `es_dueno` para mostrar el enlace «Usuarios».

## Datos (migración `backend/sql/2026-11-25_admin_usuarios.sql`)
- `users.suspendida boolean not null default false`; `users.ultimo_acceso timestamptz` (nula).
- `auditoria_admin(id bigint identity, creado_en timestamptz default now(), accion text check (...4 valores), usuario_id uuid not null)`;
  **sin llave foránea**; RLS activado sin políticas; sin permisos para `anon`/`authenticated`; índice por `(creado_en desc, id desc)`.
- Funciones (todas `SECURITY INVOKER`, `search_path = public`, `EXECUTE` solo para `service_role`): `admin_listar_usuarios(p_q, p_limite, p_desplazamiento)`,
  `admin_detalle_usuario(p_id)`, `admin_suspender_usuario(p_id)`, `admin_reactivar_usuario(p_id)`, `admin_cerrar_sesiones_usuario(p_id)`,
  `admin_eliminar_usuario(p_id, p_correo)`, `admin_auditoria(p_limite, p_desplazamiento)`, `admin_registrar_auditoria(p_accion, p_usuario_id)` (auxiliar),
  `registrar_acceso(p_id)`. Las de solo lectura (`admin_listar_usuarios`, `admin_detalle_usuario`, `admin_auditoria`) están marcadas `STABLE`.
- Las funciones de acción devuelven un texto de lista cerrada (`ok`, `no_existe`, `ya`, `pendiente`, `no_suspendida`, `correo_distinto`) que el backend traduce a 200/404/409/422.
