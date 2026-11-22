# AGENTS.md

Instrucciones para herramientas de IA distintas de Claude Code (Codex, Cursor, etc.).

Las reglas del proyecto están en [`CLAUDE.md`](CLAUDE.md) y se aplican igual aquí. Contexto completo en
[`CONTEXTO_PROYECTO_CLAUDE.md`](CONTEXTO_PROYECTO_CLAUDE.md). Resumen:

- La especificación en `spec/` es la fuente de verdad. No inventar requerimientos.
- No cambiar reglas de negocio ni contratos sin actualizar y aprobar antes la spec.
- Todo cambio con pruebas (`backend/tests/`) y trazabilidad actualizada (`spec/TRACEABILITY.md`).
- Sin cambios destructivos ni acceso a secretos. No hacer push a `main` sin aprobación (despliega a producción).
- No debilitar la seguridad existente (`spec/05-INVARIANTS.md`).
- Los perfiles de rol (coordinador, clasificador, generador, validador, revisor) están en `.claude/agents/*.md`;
  son texto plano y pueden usarse como prompt de sistema en cualquier herramienta.
