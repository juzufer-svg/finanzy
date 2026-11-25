# Finanzy — Contexto del proyecto (vigente)

> Leer SOLO por secciones y solo si hace falta (empezar por `docs/MAPA.md` y `work/ESTADO.md`). Sin claves: los valores reales
> viven en las variables de entorno de Vercel y Railway. Comportamiento exacto: `spec/` (índice en `spec/INDICE.md`).

## 1. Qué es
App web personal de control de finanzas, en español: ingresos y gastos por categoría, presupuestos mensuales, metas con abonos,
recurrentes que se confirman, cuentas de dinero con saldo y transferencias, reportes del mes, exportar CSV/Excel, asistente con IA,
registro por WhatsApp, Monitor de consumos y panel de usuarios (ambos solo para el Dueño). Los montos se guardan en COP y se convierten al mostrarlos.
- Producción: https://finanzyapp.vercel.app · repositorio https://github.com/juzufer-svg/finanzy (rama `main`).
- Cada `git push` a `main` despliega solo (Vercel ≈ 45 s, Railway ≈ 40 s).

## 2. Arquitectura e infraestructura
```
Navegador ─► Vercel (Next.js, /frontend) ─ rewrite /api/v1/* (servidor a servidor, sin CORS) ─► Railway (FastAPI, /backend, Dockerfile, Python 3.11)
                                                                                                  ├─► Supabase (PostgreSQL)
                                                                                                  └─► Brevo (correo por API HTTPS)
```
| Servicio | Uso | Plan | Notas |
|---|---|---|---|
| Vercel | Frontend | Hobby, US$0 | Node ≥ 20.9; Root Directory = `frontend` |
| Railway | Backend | Hobby, US$5/mes | Bloquea SMTP: el correo va por API HTTPS |
| Supabase | PostgreSQL | Free, US$0 | Se pausa tras 7 días sin actividad (keepalive en `.github/workflows/`); respaldo semanal en Actions (`docs/RESPALDOS_SUPABASE.md`) |
| Brevo | Códigos por correo | Free | 300 correos/día |
| Anthropic | Asistente y WhatsApp | Prepago por tokens | Opcional; costos en `docs/COSTOS_ASISTENTE.md`; fijar límite de gasto en la Claude Console |
| Meta WhatsApp Cloud API | Registro por WhatsApp | Número de prueba | Guía `docs/WHATSAPP.md` |

**Variables de entorno (solo nombres).** Railway: `ENVIRONMENT=production`, `SECRET_KEY` (≥ 32), `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
`SUPABASE_URL`, `SUPABASE_KEY` (service_role), `SUPABASE_ANON_KEY`, `BREVO_API_KEY`, `FROM_EMAIL`, `FROM_NAME`; opcionales:
`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `ASISTENTE_PREGUNTAS_POR_USUARIO_DIA`, `ASISTENTE_PREGUNTAS_TOTALES_DIA`; WhatsApp: `WHATSAPP_TOKEN`,
`WHATSAPP_APP_SECRET`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_MENSAJES_POR_DIA`, `WHATSAPP_MENSAJES_TOTALES_DIA`;
Dueño y Monitor: `OWNER_EMAIL` (único correo con acceso; vacío = nadie), `MONITOR_RAILWAY_TOKEN`, `MONITOR_RAILWAY_PROJECT_ID`,
`MONITOR_ANTHROPIC_ADMIN_KEY`, `MONITOR_META_TOKEN`, `MONITOR_META_WABA_ID`, `MONITOR_VERCEL_TOKEN`, `MONITOR_VERCEL_TEAM_ID`,
`MONITOR_BREVO_KEY` (tokens de solo lectura), `MONITOR_SUPABASE_LIMITE_BD_BYTES` (por defecto 500 MB). Vercel: `BACKEND_URL` (con `https://`).

## 3. Stack
- Frontend: Next.js 16 (App Router), React 19, TypeScript, Tailwind 3.4, Zustand, Axios; ESLint 9 con reglas del React Compiler (0 problemas);
  `proxy.ts` redirige `/login` y `/register` a `/auth/*`; cabeceras de seguridad (CSP, HSTS, etc.) en `next.config.js`.
- Backend: FastAPI, Pydantic 2, PyJWT, bcrypt, supabase-py, httpx, openpyxl (exportar). `requirements.txt` (producción) y `requirements-dev.txt` (pytest, pip-audit).
- El backend es el único que habla con la BD (clave service_role). Modo demo en memoria (`models/demo_db.py`) solo en desarrollo.

## 4. Base de datos (Supabase / PostgreSQL)
Esquema de referencia `PLATAAPP_SCHEMA.sql`; cambios como migraciones manuales en `backend/sql/` (se ejecutan en el SQL Editor **antes** del push que las usa; se prueban con `backend/sql/pruebas/probar.sh`). Las tablas de datos tienen `usuario_id → users(id) ON DELETE CASCADE`.
| Tabla | Contenido clave |
|---|---|
| `users` | email único en minúsculas, `hashed_password` (bcrypt), `full_name`, `currency`, `is_active`, `session_version`, `suspendida`, `ultimo_acceso` |
| `categorias` / `presupuestos` / `metas` | categoría (`tipo` ingreso/gasto); presupuesto (`limite_mensual`, `mes_ano` `YYYY-MM`, UNIQUE por categoría y mes); meta (`monto_objetivo`, `monto_actual`, `estado` sin uso, BL-008) |
| `transacciones` | `monto NUMERIC(12,2)`, `fecha`, `tipo`, `categoria_id` (SET NULL), `medio_pago` opcional, `cuenta_id` opcional |
| `recurrentes` | frecuencia mensual/quincenal/semanal, `proxima_fecha`, `activa`; RLS sin políticas |
| `cuentas` / `transferencias` | cuenta de dinero (`tipo`, `saldo_inicial`, `archivada`; saldo derivado, nunca guardado); transferencia entre dos cuentas propias; llaves compuestas `(id, usuario_id)` |
| `auth_login_intentos`, `auth_codigos`, `auth_limites_eventos` | estado de autenticación persistente (funciones `auth_*` solo `service_role`) |
| `whatsapp_enlaces`, `whatsapp_mensajes`, `whatsapp_registros` | enlace del número, mensajes y registros del agente |
| `contadores_diarios`, `auditoria_admin` | contadores agregados del Monitor; auditoría del panel de usuarios |
- Funciones SQL atómicas solo para `service_role` (nunca `EXECUTE` a `anon`/`authenticated`): `abonar_meta`, funciones de cuentas, transferencias y confirmar recurrente, `auth_*`.
- Las cuentas sin verificar (`is_active = false`) se borran solas tras 1 hora. Esquema privado `respaldo` para copias de borrados.
- Columna sobrante `presupuestos."mes_año"` (BL-019): no usarla.
- Cambiar una contraseña a mano (también cierra sus sesiones): `update users set hashed_password = extensions.crypt('Nueva', extensions.gen_salt('bf', 12)), is_active = true, session_version = session_version + 1 where email = '…';`

## 5. API (prefijo `/api/v1`)
El navegador no llama al backend: usa el proxy de Next.js, que convierte la cookie `__Host-finanzy_session` en `Authorization: Bearer` y quita el token de las respuestas. Rutas propias del proxy: `POST /auth/logout` y `POST /auth/adopt`.
Contratos exactos en `spec/CONTRACTS/` (CT-001…013); prefijos: `/auth`, `/users/me`, `/transacciones`, `/categorias`, `/presupuestos`, `/metas`, `/recurrentes`, `/cuentas`, `/transferencias`, `/exportaciones/transacciones`, `/asistente/chat`, `/whatsapp` (webhook de Meta directo a Railway, firma `X-Hub-Signature-256`), `/monitor` y `/admin` (solo Dueño, 404 a los demás), `/health`. `/docs` y `/openapi.json` ocultos en producción.

## 6. Flujos clave
- Registro: usuario inactivo → código de 6 dígitos (10 min) → `verify-email` activa y entrega sesión. Login con cuenta sin verificar reenvía código (`status: pending`).
- Recuperar contraseña: código por correo, respuesta genérica, mínimo 8 caracteres; cierra todas las sesiones y desconecta WhatsApp.
- Sesión: JWT HS256 de 7 días en cookie HttpOnly + Secure + SameSite=Lax con la versión de sesión (`sv`).

## 7. Estructura de carpetas
Ver `docs/MAPA.md` (carpetas y tema → archivos → spec); no se duplica aquí.

## 8. Seguridad implementada (no deshacer; detalle en `spec/05-INVARIANTS.md`)
- Sin endpoints de diagnóstico; verificación de dueño (anti-IDOR) en toda operación por ID (404 si no es suyo) y filtro por `usuario_id` en la BD (INV-001, 021).
- Validación Pydantic: montos, tipos, fechas y meses, longitudes, rango de fechas (INV-003 a 005, 063).
- Estado de autenticación persistente en PostgreSQL (INV-037 a 041, ADR-010): bloqueo de login (5 fallos en 24 h → 15 min), códigos de un solo uso (5 intentos) y límites de envío sobreviven a despliegues; correo e IP solo como huella HMAC (clave derivada de `SECRET_KEY`: rotarla pierde bloqueos y códigos pendientes); fail-closed: si falla la BD de estado o se pasa el plazo (4 s por llamada) las rutas de auth responden 503. Tras el SQL `2026-11-24_auth_persistente.sql`. Limitadores en memoria del asistente, WhatsApp y Monitor: BL-040.
- Límites de correos: 10 pedidos/IP/hora, 60 s entre códigos al mismo correo, 10/día por destinatario, 250/día global; 30 intentos de login/verificación por IP cada 10 min (`core/rate_limit.py`).
- JWT con PyJWT: solo HMAC, exige `exp` y `sub`. Cierre de sesiones por `session_version` en cada ruta protegida (401 si no coincide; 503 si Supabase falla). Cuenta suspendida: sin login ni sesiones (INV-056).
- Token fuera de JavaScript (INV-020): cookie HttpOnly vía proxy; todo cambio de datos exige `x-finanzy-csrf` y `Origin` propio.
- Configuración que nunca impide arrancar (INV-019); en producción sin `BREVO_API_KEY` el código nunca va a los logs.
- Operaciones de dinero atómicas en PostgreSQL: abono a metas (INV-008), cuentas, transferencias y confirmar recurrentes (INV-046 a 052). Trabajo pesado con ejecutores acotados y 503 sin encolar.
- Monitor y panel de usuarios solo para el Dueño (INV-031 a 036, 053 a 062): sin tokens ni datos personales en respuestas y logs.
- Exportación solo de lo propio y con neutralización de fórmulas (INV-042 a 045). WhatsApp solo con firma de Meta y número enlazado (INV-029).
- CI (`.github/workflows/ci.yml`): pytest, pip-audit, eslint y next build en cada PR y push a `main`. Frontend sin clave de Supabase y sin `alert`/`confirm`.

## 9. Convenciones de código y diseño
- Idioma: interfaz, errores, comentarios y docs en español.
- Frontend: API solo con `apiClient` (`@/lib/api-client`) y rutas relativas `/api/v1/...`; nunca leer ni guardar el token. Errores con `apiErrorMessage`, avisos con `notify()`, confirmaciones con `await confirm({...})` de `useDialog()`, fallos de carga con `<ErrorState onRetry>`. Cargas con `useCallback((isActive = () => true) => …)` y guardia `let active = true … return () => { active = false }` en el `useEffect`.
- Accesibilidad: `<label htmlFor>` + `id`, `autoComplete`, foco visible (`focus-visible:`), radios `sr-only`, `role="alert"`/`aria-live`.
- Diseño: clases de `globals.css` (`card`, `btn-primary/secondary/danger`, `input-field`, `label`, `page-title`, `page-subtitle`, `badge-*`). Cada vista usa `<PageHeader>` y, si depende del mes, `<PeriodPicker />` con el mes de `usePeriodStore` (nunca un `useState` propio); `monthTitle()` y `shortDate()` de `lib/month-stats.ts`. Un solo logo por pantalla; el menú móvil se cierra en cada cambio de ruta; iPhone: `viewport-fit=cover`, `env(safe-area-inset-*)`, campos a 16 px; modales `max-h-[calc(100dvh-2rem)]`.
- Colores: azul marino `#0D1B4B`, verde azulado `#00B89C`, primario `#2563eb`; modo oscuro por clase `dark` (`globals.css` fuerza `.dark .bg-white`; para fondos que deben seguir blancos usar `bg-[#fff]`).
- Backend: rutas finas en `api/routes`, datos en `models`, validación en `schemas`; `usuario_id` del token y `_ensure_owner(...)` por ID; correos con `_issue_code(...)` y `rate_limit.py`; fechas con `datetime.now(timezone.utc)`.
- Antes de terminar: pruebas del backend, `npx eslint .` y `npx next build`.

## 10. Desarrollo local
```powershell
cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000   # sin Supabase: BD demo; el código de correo sale por consola
cd frontend; npm install; npm run dev                              # BACKEND_URL por defecto http://localhost:8000
```

## 11. Metodología y pendientes
SDD con agentes (ADR-004): `CLAUDE.md`, `docs/PROTOCOLO-AGENTES.md`, `docs/CICLO-SDD.md`. Pendientes vivos: `work/BACKLOG.md` y `work/ESTADO.md`.
Reglas: no introducir librerías sin justificación (reutilizar `DialogProvider`, `ErrorState`, `apiClient`); sin claves ni correos personales en código o docs; todo cambio de comportamiento actualiza la spec y `spec/TRACEABILITY.md` con pruebas.
