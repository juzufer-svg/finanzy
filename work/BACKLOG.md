# Backlog y cambios en curso

Lo mantiene el Coordinador. Detalle de cada cambio en `work/changes/CHG-NNN-slug.md`.
Para empezar cualquiera: `/sdd-nuevo-cambio <título o descripción>`.

| ID | Título | Tipo | Riesgo | Estado | Origen |
|---|---|---|---|---|---|
| BL-001 | Evitar la pausa de Supabase por inactividad (tarea programada en GitHub Actions) | nueva-funcionalidad | medio | Pendiente | REQ-N-007 |
| BL-002 | Respaldo semanal automático de la base de datos + prueba de restauración | nueva-funcionalidad | alto | Pendiente | REQ-N-008 |
| BL-003 | Cerrar las sesiones abiertas al cambiar la contraseña (versión de sesión por usuario) | cambio-de-regla | alto | En revisión (CHG-001) | Pregunta abierta 4 |
| BL-004 | CI en GitHub Actions: pytest + pip-audit del backend, lint + build del frontend en cada push | deuda-tecnica | medio | Pendiente | REQ-N-009 |
| BL-005 | Revisar RLS de Supabase con Security Advisor | deuda-tecnica | medio | Pendiente | Contexto §11 |
| BL-006 | Unificar la longitud mínima de contraseña (registro 6 vs. recuperación 8) | cambio-de-regla | medio | Pendiente | Pregunta abierta 1 |
| BL-007 | Gasto diario promedio con los días reales del mes | correccion-de-bug | bajo | Pendiente | Pregunta abierta 2 |
| BL-008 | Decidir el uso o eliminación de la columna `metas.estado` | deuda-tecnica | medio | Pendiente | Pregunta abierta 3 |
| BL-009 | Limpiar los documentos antiguos de la raíz (`API_REFERENCE.md`, `ARCHITECTURE.md`, `QUICKSTART.md`, `START_HERE.md`, `*.sh`, …) y actualizar `README.md` | deuda-tecnica | bajo | Pendiente | ADR-004 |
| BL-010 | Pruebas automatizadas del frontend (avance de presupuestos, reportes, moneda) | deuda-tecnica | medio | Pendiente | TRACEABILITY (huérfanos) |
| BL-011 | Quitar de la lista de CORS los dominios viejos `plataapp*.vercel.app` | deuda-tecnica | bajo | Pendiente | `backend/app/main.py` |
