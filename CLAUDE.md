# CLAUDE.md — Finanzy

> Breve a propósito. Empezar por `docs/MAPA.md` (mapa) y `work/ESTADO.md` (estado). Arquitectura, BD e infraestructura: `CONTEXTO_PROYECTO_CLAUDE.md` por secciones.
> Especificación (fuente de verdad del comportamiento): `spec/`. Proceso: `docs/`.

Finanzy es una app personal de finanzas: Next.js 16 (`frontend/`, Vercel) + FastAPI (`backend/`, Railway) +
Supabase (PostgreSQL) + Brevo (correo). Producción: https://finanzyapp.vercel.app · cada push a `main` despliega.

## Reglas del proyecto

1. Leer `docs/MAPA.md` y `work/ESTADO.md`; el CONTEXTO (`CONTEXTO_PROYECTO_CLAUDE.md`) solo por secciones cuando haga falta.
2. Consultar `spec/` antes de modificar funcionalidades. La especificación aprobada es la fuente de verdad.
3. No inventar requerimientos. Si falta información: listar el vacío y preguntar.
4. No modificar reglas de negocio sin autorización humana explícita.
5. Todo cambio de comportamiento debe tener pruebas (`backend/tests/`).
6. Mantener la trazabilidad (`spec/TRACEABILITY.md`) en el mismo cambio que el código (skill `sdd-trazabilidad`).
7. No alterar contratos API sin actualizar antes su especificación (`spec/CONTRACTS/`).
8. No ejecutar cambios destructivos ni tocar producción. Nunca leer ni imprimir `.env` o secretos.
   **No hacer `git push` a `main` sin aprobación explícita**: el push despliega a producción.
9. Un agente no aprueba su propio trabajo: la calidad se demuestra con pruebas y revisión independiente.
10. No debilitar la seguridad existente (ver `spec/05-INVARIANTS.md` y `CONTEXTO_PROYECTO_CLAUDE.md` §8).
11. Mantener costos mínimos (planes gratuitos); avisar antes de cualquier cosa que implique pagar.
12. Textos de la interfaz, mensajes de error, documentación y comentarios en **español**.

## Flujo obligatorio

Analizar → Especificar → Diseñar → Validar spec → Coordinar → Implementar → Validar → Revisar → Documentar → Aprobar

- Para empezar un cambio: `/sdd-nuevo-cambio <pedido>`. Para revisar la spec: `/sdd-validar-spec`.
- **Modo proporcional (tres modos, CHG-021)**: `rapido` (riesgo bajo: textos, estilos, una tarjeta o campo en pantalla, docs;
  sin clasificador ni revisor), `estandar` (riesgo medio: ficha de cambio + generador + validador) y `completo`
  (riesgo alto: autenticación, dinero, datos personales, migraciones, seguridad: ficha/spec + validador y revisor en paralelo).
  Ante la duda entre dos, el más estricto. Detalle: `docs/PROTOCOLO-AGENTES.md` y `docs/CICLO-SDD.md`.

> **Modelos:** el dueño autorizó (2026-11-25) que el coordinador rote Haiku/Sonnet/Opus por tarea sin pedir permiso (ver `docs/PROTOCOLO-AGENTES.md` «Qué modelo usar»). No cubre push a `main`, SQL en producción ni reglas de negocio.

## Los 5 agentes (`.claude/agents/`)

| Agente | Rol | Modelo | Puede escribir código |
|---|---|---|---|
| `coordinador` | Orquesta, divide tareas, mantiene estado, escala a humano | sonnet | No (solo `work/` y spec aprobada) |
| `clasificador` | Clasifica la entrada, riesgo y modo | haiku | No |
| `generador` | Implementa lo ya especificado | sonnet | Sí |
| `validador` | Protege invariantes, ejecuta pruebas, puede bloquear | sonnet | No |
| `revisor` | Audita contra spec: regresiones, seguridad, evidencia | sonnet (opus si el modo es `completo`) | No |

Modelo por defecto barato; el coordinador lo sube o baja por tarea con el parámetro `model` (haiku = mecánico, sonnet = estándar, opus = solo revisión `completo` de dinero/seguridad/migraciones, diseño con concurrencia o especificar algo ambiguo). Detalle y reglas de economía: `docs/PROTOCOLO-AGENTES.md`. La sesión principal conviene en Sonnet (`/model`); Opus solo para diseño.

## Parámetros del proyecto

- Umbral de confianza para decidir sin humano: **85 %**.
- Máximo de ciclos Generador→Validador/Revisor antes de escalar: **2** (el primero corrige todo; el segundo solo verifica lo corregido).
- Stack y decisiones: `spec/ADR/`.
- **Pruebas backend** (desde `backend/`):
  `python -m pytest -q` (dependencias: `pip install -r requirements-dev.txt`)
- **Auditoría de dependencias backend**: `python -m pip_audit -r requirements.txt`
- **Lint y build frontend** (desde `frontend/`): `npx eslint .` (debe dar 0 problemas) y `npx next build`

## Convenciones de código

**Backend**
- Capas: `schemas` (validación Pydantic) → `api/routes` (reglas, `_ensure_owner`, errores HTTP) → `models` (Supabase).
- Toda operación por ID verifica el dueño (INV-001). Los errores de Supabase se propagan; nunca guardar en memoria en producción.
- Endpoints que envían correos: usar `_issue_code(...)` y los limitadores de `core/rate_limit.py`.
- Fechas con `datetime.now(timezone.utc)`. JWT solo con `core/security.py` (PyJWT, HMAC).

**Frontend**
- API solo con `apiClient` y rutas relativas `/api/v1/...`. Errores con `apiErrorMessage`; avisos y confirmaciones con `useDialog()`; fallos de carga con `<ErrorState onRetry>`. Nunca `alert`/`confirm`.
- Cargas de datos con guardia `isActive` (ver `CONTEXTO_PROYECTO_CLAUDE.md` §9); sin `setState` síncrono en efectos.
- Accesibilidad: `<label htmlFor>` + `id`, `autoComplete`, foco visible, radios `sr-only`, `role="alert"` en errores.
- Diseño: reutilizar las clases de `globals.css` (`card`, `btn-*`, `input-field`, `label`, `page-*`) y los colores de marca.
  Para trabajo visual nuevo, seguir el flujo de skills de diseño de la configuración global del usuario.

## Mapa de la documentación

- **Mapa de la app (leer primero)** → `docs/MAPA.md` · Estado actual → `work/ESTADO.md` · Índice de la spec → `spec/INDICE.md`
- Qué hace la app → `spec/REQUIREMENTS.md` (solo con `grep`) · Dominio → `spec/01..05-*.md`
- API → `spec/CONTRACTS/` · Casos de uso → `spec/USE-CASES/` · Escenarios → `spec/BDD/`
- Decisiones técnicas → `spec/ADR/` · No funcionales → `spec/NFR/NFR.md`
- Estado de cada trabajo → `work/BACKLOG.md` y `work/changes/` (abiertas; las cerradas están en `work/archivo/`)
- Cómo trabajan los agentes → `docs/PROTOCOLO-AGENTES.md`
- Los documentos y scripts antiguos de la raíz se eliminaron (CHG-005). El esquema de referencia de la BD es
  `PLATAAPP_SCHEMA.sql` y los cambios sobre la base existente van como migraciones en `backend/sql/`.

## Al cerrar una tarea, informar siempre

Decisiones tomadas · archivos modificados · pruebas ejecutadas y resultado · pendientes · si requiere desplegar
(push a `main`) o cambiar variables de entorno.
