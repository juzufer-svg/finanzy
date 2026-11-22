---
description: Revisa la coherencia e integridad de la especificación antes de desarrollar
argument-hint: [alcance opcional: REQ-… o módulo]
---

Valida la especificación en `spec/` (alcance: $ARGUMENTS; si está vacío, todo) **sin escribir código**.

Comprueba y reporta:
1. Cada REQ tiene id único, alcance y criterios de aceptación verificables.
2. Cada REQ funcional se relaciona con al menos un UC y un escenario BDD (ver `spec/TRACEABILITY.md`).
3. Todo término usado existe en `spec/01-GLOSSARY.md`; no hay términos prohibidos.
4. Estados y transiciones (`04-STATES.md`) son consistentes con invariantes (`05-INVARIANTS.md`) y contratos.
5. No hay contradicciones entre documentos ni requerimientos ambiguos ("rápido", "fácil", "adecuado").
6. NFR medibles (valor y método de medición).
7. Preguntas abiertas pendientes y su impacto.

Entrega una tabla de hallazgos (BLOQUEANTE / IMPORTANTE / MENOR) y las preguntas que debo responder.
