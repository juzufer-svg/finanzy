# MAPA de Finanzy (leer esto primero; ~5 KB)

App web personal de finanzas (español): transacciones, presupuestos, metas, recurrentes, cuentas y transferencias, exportar, asistente IA,
WhatsApp, monitor y panel de usuarios (Dueño). Next.js (Vercel) → proxy `/api/v1/*` → FastAPI (Railway) → Supabase; Brevo envía correos. Montos en COP.

## Carpetas
- `backend/app/main.py` rutas y CORS · `api/routes/*.py` reglas y errores HTTP (un archivo por tema, ver tabla)
- `backend/app/api/sesion.py` sesión y versión · `api/dueno.py` comprueba al Dueño · `api/cuentas_errores.py` errores SQL → HTTP
- `backend/app/schemas/` validación Pydantic · `models/` acceso a Supabase (`plataapp.py` finanzas, `user.py`, `demo_db.py` solo desarrollo)
- `backend/app/core/` `config.py`, `security.py` (JWT, bcrypt), `rate_limit.py`, `supabase.py` · `utils/` lógica por tema (`email.py`, `exportar.py`, `rango_fechas.py`…)
- `backend/sql/` migraciones manuales (SQL Editor, antes del push) · `backend/sql/pruebas/probar.sh` las prueba (PostgreSQL real) · `backend/tests/` pytest
- `frontend/app/dashboard/{page,transactions,recurring,categories,budgets,goals,reports,cuentas,assistant,monitor,usuarios,profile}/page.tsx`; `app/auth/*`; `app/api/v1/[...path]/route.ts` proxy y cookie
- `frontend/lib/` `api-client.ts`, `api-error.ts`, `session.ts`, `currency.ts`, `month-stats.ts` y un módulo por tema
- `frontend/components/` (DialogProvider, ErrorState, PageHeader, PeriodPicker…) · `frontend/store/` (auth, currency, period, theme) · `frontend/tests/*.test.mjs`
- `spec/` verdad del comportamiento (ver `spec/INDICE.md`) · `work/` estado (`ESTADO.md`, `BACKLOG.md`, `changes/` abiertas, `archivo/`) · `docs/` proceso · `.claude/agents/`

## Tema → código → spec (`be`=backend/app, `fe`=frontend)
| Tema | Código | Spec |
|---|---|---|
| Auth y sesión | `be/api/routes/auth.py`, `api/sesion.py`, `core/security.py`, `models/auth_estado.py`, `fe/app/auth/*`, proxy `fe/app/api/v1/[...path]/route.ts` | INV-006 a 020, 037 a 041 · CT-001 · UC-001..003 · ADR-003/005/010 |
| Transacciones | `be/api/routes/plataapp.py`, `models/plataapp.py`, `models/transacciones_ejecutor.py`, `fe/app/dashboard/transactions` | INV-001 a 005, 022 · CT-003 · UC-004/008 |
| Categorías | `plataapp.py`, `fe/app/dashboard/categories` | INV-002, 028 · CT-004 · UC-005 |
| Presupuestos | `plataapp.py`, `fe/app/dashboard/budgets` | INV-002, 028 · CT-005 · UC-006 |
| Metas | `plataapp.py`, `fe/app/dashboard/goals` | INV-008 · CT-006 · UC-007 · WF-002 |
| Recurrentes | `be/utils/recurrencia.py`, `plataapp.py`, `fe/app/dashboard/recurring`, `fe/lib/recurrentes.ts` | INV-025/026 · CT-008 · UC-012 |
| Cuentas y transferencias | `be/api/routes/{cuentas,transferencias}.py`, `models/{cuentas,transferencias}.py`, `fe/app/dashboard/cuentas` | INV-046 a 052 · CT-012 · UC-016 · ADR-009 |
| Exportar | `be/api/routes/exportar.py`, `utils/exportar.py`, `fe/components/ExportarDescarga.tsx` | INV-042 a 045 · CT-011 · UC-015 · ADR-011 |
| Asistente IA | `be/api/routes/asistente.py`, `utils/asistente.py`, `fe/app/dashboard/assistant` | INV-023/024 · CT-007 · UC-011 · ADR-006 |
| WhatsApp | `be/api/routes/whatsapp.py`, `utils/whatsapp.py`, `models/whatsapp.py`, `fe/components/WhatsAppCard.tsx` | INV-029/030 · CT-009 · UC-013 · ADR-007 · `docs/WHATSAPP.md` |
| Monitor | `be/api/routes/monitor.py`, `utils/monitor_plataformas.py`, `fe/app/dashboard/monitor` | INV-031 a 036 · CT-010 · UC-014 · ADR-008 |
| Admin usuarios | `be/api/routes/admin_usuarios.py`, `models/admin_usuarios.py`, `fe/app/dashboard/usuarios` | INV-053 a 062 · CT-013 · UC-017 · ADR-012 |
| Rango de fechas | `be/utils/rango_fechas.py`, `fe/lib/rango-fechas.ts` | INV-063 |

## Qué leer según la tarea
1. Siempre: este mapa y `work/ESTADO.md`. Luego `spec/INDICE.md` para ubicar la pieza.
2. Una invariante: `grep -n "^| INV-049" spec/05-INVARIANTS.md` · un requisito: `grep -n "REQ-F-019" spec/REQUIREMENTS.md` · su trazabilidad: `grep -n "CT-012" spec/TRACEABILITY.md`.
3. CT, UC, ADR, BDD y WF son pequeños: léelos completos solo si la tarea los toca. Código: solo los archivos de la fila del tema.
4. Infraestructura, esquema de BD y convenciones: una sección de `CONTEXTO_PROYECTO_CLAUDE.md` (`grep -n "^## "`).
5. NUNCA leer enteros `spec/05-INVARIANTS.md`, `spec/TRACEABILITY.md`, `spec/REQUIREMENTS.md` ni `CONTEXTO_PROYECTO_CLAUDE.md`.

## Comandos
- Backend (en `backend/`): `python -m pytest -q` · `python -m pip_audit -r requirements.txt`
- Frontend (en `frontend/`): `npx eslint .` (0 problemas) · `npx next build` · `npm test`

## Seguridad que nunca se rompe
1. Toda operación por ID verifica el dueño (INV-001) y filtra por `usuario_id` en la BD.
2. El token solo en cookie HttpOnly vía proxy; nunca en JavaScript; cambios de datos con encabezado CSRF (INV-020).
3. Si Supabase falla: error (503), nunca guardar en memoria en producción (INV-013, INV-039).
4. Reglas críticas en el backend y atómicas en la base (saldos, abonos, bloqueos); nunca solo en la interfaz.
5. Sin secretos, correos ni datos personales en logs, respuestas ni documentos; nunca leer ni imprimir `.env`.
6. Monitor y panel admin solo para el Dueño, verificado en cada petición; nada de `git push` a `main` sin aprobación del dueño.
