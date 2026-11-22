# ADR-004 — Adopción de SDD con 5 agentes en modo proporcional

- **Estado:** aceptada
- **Fecha:** 2026-11-22 · **Decide:** dueño del proyecto

## Contexto
Finanzy evoluciona con ayuda de IA. Se adopta la plantilla SDD + 5 agentes (`D:\Proyecto Claude IA`) sobre un
proyecto que ya estaba en producción (no creado desde la plantilla).

## Alternativas evaluadas
| Opción | Pros | Contras |
|---|---|---|
| Plantilla tal cual | Proceso completo y uniforme | Muy pesado para cambios triviales; estructura `src/` distinta |
| Sin proceso | Rápido | Riesgo de romper seguridad o reglas sin darse cuenta |
| **Plantilla adaptada + modo proporcional** | Rigor donde hay riesgo, agilidad en lo trivial | El clasificador debe estimar bien el riesgo |

## Decisión
- Spec reconstruida desde el código como línea base (`spec/`), con invariantes respaldados por pruebas en `backend/tests/`.
- Capas de la plantilla (`domain/application/infrastructure/api`) mapeadas a las de Finanzy (ver `CLAUDE.md`).
- **Modo `ligero`** (riesgo bajo) y **modo `completo`** (riesgo medio/alto) según `docs/PROTOCOLO-AGENTES.md`.
- `git push` a `main` siempre requiere aprobación humana (despliega a producción).

## Consecuencias
- Toda funcionalidad nueva pasa por `/sdd-nuevo-cambio` y actualiza `spec/TRACEABILITY.md`.
- Los documentos antiguos de la raíz quedan como desactualizados (limpieza en el backlog).
