# ADR-001 — Stack tecnológico y arquitectura base

- **Estado:** aceptada (documenta el sistema existente)
- **Fecha:** 2026-11-22 · **Decide:** dueño del proyecto

## Contexto
App personal con un solo desarrollador, presupuesto mínimo (REQ-N-006) y despliegue automático desde GitHub.

## Decisiones
| Aspecto | Decisión | Motivo |
|---|---|---|
| Frontend | Next.js 16 (App Router) + React 19 + TypeScript + Tailwind 3.4 + Zustand + Axios, en Vercel Hobby | Gratis, despliegue automático, buen soporte de React |
| Backend | FastAPI (Python 3.11, Docker) en Railway Hobby | API sencilla y tipada; US$5/mes |
| Base de datos | Supabase (PostgreSQL) plan Free, acceso solo desde el backend con clave service_role | Gratis; el frontend no habla con la BD |
| Comunicación | El frontend llama a rutas relativas `/api/v1/*` que Vercel reenvía al backend (rewrite) | Sin CORS en el navegador; la URL del backend no se expone en el código |
| Arquitectura backend | Capas `schemas` → `api/routes` → `models`; seguridad transversal en `core/` | Simple y suficiente para el tamaño del proyecto |
| Autenticación | JWT HS256 de 7 días (PyJWT) en `localStorage`; contraseñas con bcrypt (ver ADR-003) | Sin estado en el servidor |
| Correo | Brevo por API HTTPS (ver ADR-002) | Gratis; Railway Hobby bloquea SMTP |
| Pruebas | pytest con `fastapi.testclient` y BD demo en memoria (`backend/tests/`) | Rápidas y sin depender de Supabase |
| Lint / formato | ESLint 9 (flat config) con reglas estrictas del React Compiler | 0 problemas como puerta de calidad |
| CI/CD | Push a `main` → Vercel y Railway despliegan. CI de pruebas: pendiente (backlog) | — |
| Observabilidad | Logs de Railway (`[EMAIL]`, `[EMAIL ERROR]`, `[EMAIL LIMIT]`) | Suficiente para una app personal |

## Consecuencias
- Comandos de prueba y lint en `CLAUDE.md`.
- Supabase gratis se pausa y no tiene respaldos (REQ-N-007, REQ-N-008 pendientes).
- Los límites de frecuencia y los códigos viven en memoria: se reinician en cada despliegue (aceptado para una sola instancia).
