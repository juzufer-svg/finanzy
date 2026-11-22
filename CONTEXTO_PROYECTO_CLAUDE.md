# Finanzy — Contexto del proyecto

> Documento de referencia para trabajar en Finanzy con Claude. Describe la app tal como está
> en producción (noviembre de 2026). No contiene claves ni contraseñas: los valores reales
> viven solo en las variables de entorno de Vercel y Railway.

## 1. Qué es Finanzy

App web personal de **control de finanzas**: registrar ingresos y gastos por categoría,
definir presupuestos mensuales por categoría, crear metas de ahorro con abonos, ver reportes
del mes y elegir la moneda de visualización. Interfaz en **español**.

- **App en producción:** https://finanzyapp.vercel.app
- **Repositorio:** https://github.com/juzufer-svg/finanzy (público, rama `main`)
- **Despliegue:** cada `git push` a `main` despliega solo (Vercel ≈ 45 s, Railway ≈ 40 s)

## 2. Arquitectura e infraestructura

```
Navegador ──► Vercel (Next.js, carpeta /frontend)
                 │  rewrite /api/v1/*  (servidor a servidor, sin CORS)
                 ▼
              Railway (FastAPI, carpeta /backend, Dockerfile, Python 3.11)
                 │                     │
                 ▼                     ▼
              Supabase (PostgreSQL)   Brevo (API HTTPS de correo)
```

| Servicio | Uso | Plan | Costo | Notas |
|---|---|---|---|---|
| Vercel | Frontend Next.js | Hobby | US$0 | Sin vencimiento. Necesita Node ≥ 20.9 |
| Railway | Backend FastAPI | Hobby | US$5/mes (incluye US$5 de consumo) | **Bloquea SMTP** (puertos 25/465/587/2525) → el correo va por API HTTPS |
| Supabase | Base de datos PostgreSQL | Free | US$0 | **Se pausa tras 7 días sin actividad** (se reactiva con *Restore*). Sin respaldos restaurables en el plan gratis |
| Brevo | Correos transaccionales (códigos) | Free | US$0 | 300 correos/día. Remitente verificado: Gmail del dueño |
| Anthropic (API de Claude) | Asistente del chat (CHG-010) | Prepago por uso | Por tokens (Haiku) | Opcional. Topes diarios en INV-024; fijar también un límite de gasto en la Claude Console |

**Historial de proveedores:** SendGrid se eliminó (su prueba gratis venció el 30/06/2026) y se
reemplazó por Brevo.

### Variables de entorno (solo nombres)

**Railway (backend):** `ENVIRONMENT=production`, `SECRET_KEY` (≥ 32 caracteres), `ALGORITHM`
(HS256), `ACCESS_TOKEN_EXPIRE_MINUTES`, `SUPABASE_URL`, `SUPABASE_KEY` (service_role),
`SUPABASE_ANON_KEY`, `BREVO_API_KEY`, `FROM_EMAIL`, `FROM_NAME`, `ANTHROPIC_API_KEY` (opcional, asistente),
`ANTHROPIC_MODEL` (por defecto `claude-haiku-5-5`), `ASISTENTE_PREGUNTAS_POR_USUARIO_DIA`, `ASISTENTE_PREGUNTAS_TOTALES_DIA`.

**Vercel (frontend):** `BACKEND_URL` (URL pública de Railway, con `https://`). Root Directory = `frontend`.

## 3. Stack técnico

**Frontend** (`/frontend`)
- Next.js **16.4** (App Router) + React **19**, TypeScript, Tailwind CSS 3.4, Zustand, Axios
- ESLint 9 (flat config `eslint.config.mjs`) con reglas estrictas del React Compiler → **0 problemas**
- `proxy.ts` (antes `middleware.ts`): solo redirige `/login` y `/register` a `/auth/*`
- Fuente Inter auto-alojada con `next/font`
- Cabeceras de seguridad en `next.config.js`: CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, HSTS

**Backend** (`/backend`)
- FastAPI 0.165, Pydantic 2.14, pydantic-settings, PyJWT 2.15, bcrypt 5, supabase-py 2.34, httpx
- `requirements.txt` (producción) y `requirements-dev.txt` (pytest, pip-audit) → `pip-audit`: 0 vulnerabilidades
- Acceso a datos con el cliente de Supabase usando la clave **service_role** (el backend es el único que habla con la BD)
- Modo demo en memoria (`models/demo_db.py`) cuando no hay `SUPABASE_URL`/`SUPABASE_KEY` (solo para desarrollo local)

## 4. Estructura de carpetas

```
backend/app/
  main.py                 FastAPI, CORS, /health, oculta /docs en producción
  api/routes/auth.py      registro, verificación, login, reenvío, recuperar contraseña
  api/routes/users.py     /users/me (ver, moneda, eliminar cuenta)
  api/routes/plataapp.py  transacciones, categorías, presupuestos, metas (con verificación de dueño)
  api/routes/asistente.py chat con Claude: sesión, topes de costo (CHG-010)
  utils/asistente.py      herramientas de solo lectura + ciclo de tool use con la API de Claude
  core/config.py          Settings (variables de entorno)
  core/security.py        JWT (PyJWT, solo HMAC) y hash de contraseñas (bcrypt)
  core/rate_limit.py      limitadores en memoria (ventana deslizante) + IP del cliente
  core/supabase.py        cliente de Supabase
  models/user.py          tabla users
  models/plataapp.py      tablas de finanzas (si Supabase falla → error, nunca guarda en memoria)
  models/demo_db.py       BD en memoria para desarrollo
  schemas/                validaciones Pydantic (montos > 0, tipo, fechas YYYY-MM-DD, meses YYYY-MM)
  utils/email.py          códigos (secrets) y envío por Brevo
backend/tests/            pruebas pytest (una por invariante; ver spec/TRACEABILITY.md)
spec/  work/  docs/  .claude/   metodología SDD (ver §12)

frontend/
  app/page.tsx                    landing
  app/auth/{login,register,forgot-password}/page.tsx
  app/dashboard/layout.tsx        sidebar, menú móvil, protección de sesión
  app/dashboard/{page,transactions,budgets,goals,reports,profile}
  components/DialogProvider.tsx   confirmaciones y avisos (toasts) propios: useDialog(), apiErrorMessage()
  components/ErrorState.tsx       bloque de error con "Reintentar"
  components/PageHeader.tsx       encabezado común de las vistas: título, subtítulo y acciones (CHG-008)
  components/PeriodPicker.tsx     selector de período: flechas, calendario de meses y "Mes actual" (CHG-009)
  store/period.ts                 período (mes) compartido por todas las vistas, en sessionStorage (CHG-009)
  components/…                    BudgetCard, DashboardSummary, GoalProgressCard, TransactionForm, TransactionList, FinanzyLogo, ThemeProvider
  app/api/v1/[...path]/route.ts   proxy al backend: guarda el JWT en cookie HttpOnly y lo envía como Bearer; CSRF (ADR-005)
  lib/api-client.ts               Axios con encabezado CSRF; migra sesiones antiguas; 401 → va a /auth/login
  lib/session.ts                  constantes de sesión (encabezado CSRF, claves de localStorage)
  lib/code-input.ts               lógica de las 6 casillas del código (admite pegar/autocompletar)
  lib/month-stats.ts              cálculos del mes: promedio diario real, proyección, vs mes anterior, acumulado, buscador (CHG-006)
  lib/payment-methods.ts          medios de pago y sus etiquetas (CHG-007)
  components/SpendingChart.tsx    gráfico SVG propio del gasto acumulado con línea de presupuesto (sin librerías)
  tests/month-stats.test.mjs      pruebas del frontend: `npm test` (node --test, sin dependencias)
  lib/currency.ts                 tasas de cambio (open.er-api.com, caché 4 h, valores de respaldo)
  store/auth.ts                   datos no sensibles del usuario (el token NO está en el navegador)
  store/currency.ts               moneda de visualización; los montos se guardan en base COP
  store/theme.ts                  modo claro/oscuro (clase `dark`)
```

## 5. Base de datos (Supabase / PostgreSQL)

Esquema de referencia en `PLATAAPP_SCHEMA.sql`. Todas las tablas de datos tienen `usuario_id` → `users(id) ON DELETE CASCADE`.

| Tabla | Columnas principales |
|---|---|
| `users` | id, email (único, en minúsculas), hashed_password (bcrypt), full_name, currency, is_active, session_version (entero, sube al restablecer la contraseña), created_at |
| `categorias` | id, usuario_id, nombre, icono, tipo (`ingreso`/`gasto`) |
| `transacciones` | id, usuario_id, categoria_id (SET NULL), monto NUMERIC(12,2), descripcion, fecha DATE, tipo, medio_pago (opcional: `debito`, `credito`, `efectivo`, `transferencia`, `nequi_daviplata`) |
| `presupuestos` | id, usuario_id, categoria_id, limite_mensual, mes_ano (`YYYY-MM`) |
| `metas` | id, usuario_id, nombre, monto_objetivo, monto_actual, fecha_objetivo, estado |

- Cada usuario recibe sus categorías por defecto la primera vez que las pide.
- Llaves foráneas y registros huérfanos (CHG-005, PR #9): la base real no tenía FKs y había 64 filas huérfanas. Scripts `backend/sql/2026-11-22_huerfanos_{1_diagnostico,2_respaldo_y_borrado,3_llaves_foraneas}.sql` (en ese orden) + `2026-11-22_quitar_vista_resumen.sql`. El paso 2 copia lo borrado al esquema privado `respaldo` (sin acceso para `anon`/`authenticated`). Se prueban en CI con PostgreSQL (`backend/sql/pruebas/probar.sh`). La columna sobrante `presupuestos."mes_año"` queda pendiente (BL-019). **Ejecutados en Supabase el 2026-11-22** (junto con `2026-11-22_medio_pago.sql`).
- Las cuentas sin verificar (`is_active = false`) se borran solas tras 1 hora.
- Cambiar una contraseña a mano (SQL Editor; también cierra sus sesiones): `update users set hashed_password = extensions.crypt('Nueva', extensions.gen_salt('bf', 12)), is_active = true, session_version = session_version + 1 where email = '…';`
- Migraciones manuales en `backend/sql/` (se ejecutan en el SQL Editor **antes** del push que las usa).
- Función `public.abonar_meta(meta, usuario, monto, fecha, descripcion)` (`backend/sql/2026-11-22_abonar_meta_atomico.sql`, CHG-004): abono en una sola transacción con la meta bloqueada. Solo la ejecuta `service_role`; **nunca** dar `EXECUTE` a `anon`/`authenticated` (recibe el `usuario_id` como parámetro). Sin la función, el backend usa el método anterior.

## 6. API (prefijo `/api/v1`, autenticación `Authorization: Bearer <JWT>`)

El navegador no llama al backend: usa el proxy de Next.js, que convierte la cookie `__Host-finanzy_session` en el
encabezado Bearer y quita el token de las respuestas de `login`/`verify-email`. Rutas propias del proxy:
`POST /api/v1/auth/logout` y `POST /api/v1/auth/adopt` (ver `spec/CONTRACTS/CT-001-auth.md`).

**Auth (`/auth`)**: `POST register`, `POST verify-email`, `POST resend-code`, `POST login`,
`POST forgot-password`, `POST reset-password`

**Usuario (`/users`)**: `GET me`, `PUT me/currency`, `DELETE me`

**Finanzas**: `transacciones` (GET con `?mes=YYYY-MM`, POST, GET/PUT/DELETE `/{id}`, GET `resumen/{mes}`; campo opcional `medio_pago`, CT-003 v1.1),
`categorias` (GET, POST, PUT/DELETE `/{id}`), `presupuestos` (GET `/{mes_ano}`, POST, PUT/DELETE `/{id}`),
`metas` (GET, POST, PUT/DELETE `/{id}`, POST `/{id}/abonar` → crea un gasto en la categoría "Ahorro" y suma a la meta)

**Asistente (`/asistente`)**: `POST chat` → pregunta en lenguaje natural; Claude consulta herramientas de solo lectura (CT-007)

**Otros**: `GET /health`. `/docs` y `/openapi.json` están ocultos en producción.

## 7. Flujos clave

- **Registro**: crea usuario inactivo → envía código de 6 dígitos (10 min) → `verify-email` activa y devuelve JWT.
- **Login**: si la cuenta no está verificada, reenvía código y responde `status: pending`.
- **Recuperar contraseña**: `/auth/forgot-password` → código por correo (prefijo interno `reset:`) → nueva contraseña (mín. 8). Respuesta genérica (no revela si el correo existe).
- **Sesión**: JWT HS256 de 7 días en una cookie HttpOnly + Secure + SameSite=Lax (ADR-005), con la versión de sesión del usuario (`sv`). Restablecer la contraseña sube la versión y cierra todas las sesiones abiertas (INV-016).
- **Moneda**: los montos se almacenan en **COP** y se convierten a la moneda elegida al mostrarlos.

## 8. Seguridad implementada (no deshacer)

- Endpoints de diagnóstico eliminados (antes exponían correos y permitían resetear contraseñas).
- **Verificación de dueño (anti-IDOR)** en toda operación por ID: si el registro no es del usuario → 404. Al crear transacciones/presupuestos se valida que la categoría sea suya.
- Validación de datos con Pydantic (montos > 0 y ≤ 1e12, tipos permitidos, formatos de fecha/mes, longitudes).
- Bloqueo de login: 5 fallos por correo → 15 min.
- Códigos con `secrets`, un solo uso, se invalidan tras 5 intentos.
- **Límites de envío de correos** (`core/rate_limit.py`): 10 pedidos de código por IP/hora, 60 s entre códigos al mismo correo, 10 correos/día por destinatario, tope global 250/día; 30 intentos de login/verificación/reseteo por IP cada 10 min.
- JWT con PyJWT: solo algoritmos HMAC, exige `exp` y `sub`.
- **Cierre de sesiones al restablecer la contraseña** (`api/sesion.py`): toda ruta protegida compara el `sv` del token con `users.session_version`; si no coincide o el usuario ya no existe → 401; si Supabase falla → 503 (no cierra la sesión).
- En producción sin `BREVO_API_KEY` el código **nunca** se escribe en logs.
- **Configuración segura que nunca impide arrancar** (`core/config.py`, INV-019): `SECRET_KEY` vacía o de ejemplo → clave aleatoria temporal; solo HMAC; sesión 5 min–30 días; CORS sin comodines ni regex; `DEBUG` apagado en producción. Avisos `[CONFIG]` en los logs de Railway.
- Toda consulta por ID filtra también por `usuario_id` en la base de datos (defensa en profundidad); un token de una cuenta no activa recibe 401 (INV-017).
- **Token fuera del alcance de JavaScript** (INV-020): cookie HttpOnly gestionada por el proxy de Next.js; toda petición que cambia datos exige el encabezado `x-finanzy-csrf` y un `Origin` propio.
- Abono a metas atómico en PostgreSQL (INV-008, CHG-004).
- CI en GitHub Actions (`.github/workflows/ci.yml`): pytest, pip-audit, eslint y next build en cada PR y push a `main`.
- Frontend sin la clave de Supabase; cabeceras de seguridad; diálogos propios (sin `alert`/`confirm`).

## 9. Convenciones de código y diseño

- **Idioma**: textos de la interfaz, mensajes de error y comentarios en español.
- **Frontend**
  - Llamadas a la API siempre con `apiClient` (`@/lib/api-client`), rutas relativas `/api/v1/...` (un `fetch` directo que cambie datos recibe 403 por CSRF). Nunca leer ni guardar el token en el navegador.
  - Errores: `apiErrorMessage(err, 'mensaje por defecto')`; avisos con `notify()`; confirmaciones con `await confirm({...})` de `useDialog()`; fallos de carga con `<ErrorState onRetry>`.
  - Cargas de datos: `useCallback((isActive = () => true) => apiClient.get(...).then(...))` y en el `useEffect` una guardia `let active = true … return () => { active = false }` (evita respuestas tardías y cumple las reglas del React Compiler).
  - Accesibilidad: cada `<label>` con `htmlFor` + `id` en el campo, `autoComplete`, foco visible (`focus-visible:`), radios con `sr-only` (no `hidden`), avisos con `role="alert"`/`aria-live`.
  - Clases utilitarias propias en `globals.css`: `card`, `btn-primary`, `btn-secondary`, `btn-danger`, `input-field`, `label`, `page-header`, `page-title`, `page-subtitle`, `badge-*`.
  - Diseño responsive (CHG-008): cada vista usa `<PageHeader>` y, si depende del mes, `<PeriodPicker />` con `wideActions`; el mes se lee de `usePeriodStore` (nunca un `useState` propio, CHG-009); títulos de mes con `monthTitle()` ("Noviembre de 2026", nunca la clase `capitalize`) y fechas de listas con `shortDate()` ("5 nov"), ambos en `lib/month-stats.ts`. El logo aparece una sola vez por pantalla (barra lateral en PC, barra superior en el celular). Botones de fila con `reveal-on-hover` (en táctil siempre visibles). iPhone: `viewport-fit=cover` + `env(safe-area-inset-*)` en barra superior, barra inferior, menú y modales; campos a 16 px en pantallas pequeñas (evita el zoom de Safari); la página desplaza la ventana, no un contenedor interno. Modales con `max-h-[calc(100dvh-2rem)]`.
  - Colores de marca: azul marino `#0D1B4B`, verde azulado `#00B89C`; primario Tailwind `#2563eb`. Modo oscuro por clase `dark` (ojo: `globals.css` fuerza `.dark .bg-white` a oscuro; para fondos que deben seguir blancos usar `bg-[#fff]`).
  - Antes de terminar: `npx eslint .` (0 problemas) y `npx next build`.
- **Backend**
  - Rutas finas en `api/routes`, acceso a datos en `models`, validación en `schemas`.
  - Toda ruta protegida obtiene `usuario_id` del token y usa `_ensure_owner(...)` en operaciones por ID.
  - Nuevos endpoints que envíen correos deben pasar por `_issue_code(...)` y los límites de `rate_limit.py`.
  - Fechas con `datetime.now(timezone.utc)` (no `utcnow`).

## 10. Desarrollo local

```powershell
# Backend (sin Supabase usa la BD demo en memoria; el código de correo aparece en consola)
cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest          # pruebas (103)
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# Frontend (BACKEND_URL por defecto http://localhost:8000)
cd frontend; npm install; npm run dev
```

## 11. Pendientes conocidos

La lista viva está en `work/BACKLOG.md`. Los principales:

1. **Supabase gratis** (BL-001, BL-002): evitar la pausa por inactividad y respaldo semanal automático.
2. ~~Cerrar sesiones al cambiar la contraseña~~ (BL-003, hecho en CHG-001).
3. ~~CI~~ (BL-004, hecho en CHG-002). ~~Cookies HttpOnly~~ (BL-012, CHG-003). ~~Abono atómico~~ (BL-013, CHG-004).
3b. Códigos y límites persistentes en PostgreSQL (BL-014). ~~FKs/huérfanos (BL-015) y limpieza (BL-009)~~: hechos en PR #9, SQL ejecutados en Supabase el 2026-11-22.
4. **Revisar RLS** en Supabase (BL-005).
5. Preguntas abiertas de la spec (BL-006, BL-008) y decidir la columna `presupuestos."mes_año"` (BL-019).

## 12. Metodología: SDD con 5 agentes (Claude Code)

Finanzy usa desarrollo guiado por especificaciones (ADR-004), adaptado de la plantilla `D:\Proyecto Claude IA`:

- **Fuente de verdad del comportamiento:** `spec/` — `REQUIREMENTS.md` (REQ-F/REQ-N), `05-INVARIANTS.md`
  (INV-001…016, cada uno con su prueba), `CONTRACTS/` (CT-001…006), `USE-CASES/`, `BDD/`, `ADR/`, `TRACEABILITY.md`.
- **Agentes** (`.claude/agents/`): coordinador, clasificador, generador, validador y revisor.
- **Comandos:** `/sdd-nuevo-cambio <pedido>` (ciclo completo) y `/sdd-validar-spec`. Skill: `sdd-trazabilidad`.
- **Modo proporcional:** riesgo bajo (textos, estilos, docs) → modo `ligero`; datos, dinero, seguridad,
  contratos o infraestructura → modo `completo` con aprobación de la spec.
- **Pruebas:** `backend/tests/` (pytest, 64 pruebas) — `cd backend; python -m pytest`.
- **Reglas para agentes:** `CLAUDE.md` (y `AGENTS.md` para otras herramientas). `git push` siempre con aprobación.

## 13. Cómo pedir cambios (para Claude)

- Leer este documento y revisar el código real antes de proponer cambios; respetar la sección 8 y `spec/05-INVARIANTS.md`.
- No introducir librerías nuevas sin justificación; reutilizar `DialogProvider`, `ErrorState`, `apiClient`.
- No poner claves, contraseñas ni correos personales en el código ni en la documentación.
- Todo cambio de comportamiento actualiza la spec y `spec/TRACEABILITY.md` y trae pruebas.
- Al terminar un cambio: pruebas del backend, lint + build del frontend, y comprobar en producción tras el despliegue.

## 14. Registro de cambios recientes

- **2026-11-22 · PR #5 (CHG-002)**: configuración segura que nunca impide arrancar, filtro por dueño en la BD, cuenta activa, moneda sin éxito falso, contraseña 8-128, CI en GitHub Actions.
- **2026-11-22 · PR #6 (CHG-003)**: sesión en cookie HttpOnly con proxy de Next.js y CSRF; el token ya no está en el navegador.
- **2026-11-22 · PR #7 (CHG-004)**: abono a metas atómico con la función SQL `abonar_meta`. SQL ejecutado en Supabase y fusionado; CI en verde.
- **2026-11-22 · PR #2 cerrado** sin fusionar: lo útil ya está en PR #5, #6 y #7.
- **2026-11-22 · PR #9 (CHG-005/006/007, fusionado; todos sus SQL ejecutados en Supabase)**: limpieza de código y documentos sin uso; SQL de registros huérfanos con respaldo y llaves foráneas; Reportes con promedio diario real, proyección al cierre, comparación con el mes anterior (hasta el mismo día) y gráfico acumulado con presupuesto; buscador y filtros en Transacciones; medio de pago (columna `medio_pago`, ejecutar `2026-11-22_medio_pago.sql` antes de fusionar). 121 pruebas backend + 14 frontend; revisión independiente aprobada con observaciones, ya corregidas.
- **2026-11-22 · PR #10 (CHG-008, diseño en PC y iPhone, fusionado)**: un solo logo por pantalla (antes salía dos veces en PC; en el celular el ícono se veía cortado por ids de degradado repetidos); "Noviembre de 2026" en vez de "Noviembre De 2026"; encabezados y navegación de mes iguales en todas las vistas; barra superior con sección actual, botón de modo claro/oscuro y acceso al perfil; barra inferior del celular de 5 botones sin textos cortados; zona segura del iPhone, sin zoom al escribir, editar/eliminar visibles en pantallas táctiles, avisos que no tapan la barra inferior; tarjetas de resumen legibles en el celular; fechas "5 nov". Solo frontend: sin cambios de API, base de datos ni variables de entorno.
- **2026-11-22 · CHG-009 (filtro de período, PR pendiente)**: el mes elegido es uno solo para Dashboard, Transacciones, Presupuestos y Reportes; se mantiene al navegar y al recargar (sessionStorage), vuelve al mes actual en una pestaña nueva o al cerrar sesión. Nuevo selector con calendario de meses, cambio de año y "Mes actual". Corrige que Presupuestos usara el mes en UTC. Solo frontend.
