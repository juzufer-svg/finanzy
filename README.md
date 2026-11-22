# Finanzy

App personal de finanzas: registra ingresos y gastos por categoría y medio de pago, define presupuestos
mensuales, crea metas de ahorro y revisa reportes del mes. Interfaz en español.

- **Producción:** https://finanzyapp.vercel.app (cada push a `main` despliega)
- **Frontend:** Next.js 16 en Vercel (carpeta `frontend/`)
- **Backend:** FastAPI en Railway (carpeta `backend/`, `Dockerfile` + `railway.json`)
- **Base de datos:** Supabase (PostgreSQL) · **Correo:** Brevo

## Documentación

| Qué | Dónde |
|---|---|
| Contexto completo (arquitectura, API, BD, seguridad, convenciones) | [`CONTEXTO_PROYECTO_CLAUDE.md`](CONTEXTO_PROYECTO_CLAUDE.md) |
| Reglas para trabajar en el proyecto | [`CLAUDE.md`](CLAUDE.md) · [`AGENTS.md`](AGENTS.md) |
| Especificación (fuente de verdad) | [`spec/`](spec/) |
| Proceso y agentes | [`docs/`](docs/) |
| Estado de los trabajos | [`work/BACKLOG.md`](work/BACKLOG.md) |
| Esquema de la base de datos | [`PLATAAPP_SCHEMA.sql`](PLATAAPP_SCHEMA.sql) y migraciones en [`backend/sql/`](backend/sql/) |
| Respaldos de Supabase | [`docs/RESPALDOS_SUPABASE.md`](docs/RESPALDOS_SUPABASE.md) |
| Costos del asistente con Claude | [`docs/COSTOS_ASISTENTE.md`](docs/COSTOS_ASISTENTE.md) |

## Desarrollo local (PowerShell)

```powershell
# Backend: sin SUPABASE_URL/SUPABASE_KEY usa una base de datos de prueba en memoria
cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# Frontend (BACKEND_URL por defecto http://localhost:8000)
cd frontend; npm install; npm run dev
```

## Comprobaciones (las mismas que corre GitHub Actions)

```powershell
cd backend; python -m pytest -q; python -m pip_audit -r requirements.txt
cd frontend; npx eslint . --max-warnings=0; npm test; npx next build
```
