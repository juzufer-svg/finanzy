# CHG-028 — Menos tokens: mapa de contexto, modelos por complejidad y limpieza de lo que ya no se usa

- **Estado:** en-implementación (pedido y aprobación explícitos del dueño el 2026-11-25)
- **Riesgo:** bajo (proceso y documentación) + medio (borrado de código sin uso) · **Modo:** `rapido` para T1 (docs/proceso) y `estandar` para T2 (limpieza de código con pruebas)

## 1. Pedido original (literal)
> ME gustaría aplicar todas las mejoras posibles para evitar desperdiciar tantos tokens y la idea es que se vayan turnando entre modelo Haiku sonnet y opus de acuerdo a la complejidad de la tarea y se cree el contexto siempre de la app para que no tenga que oler todo si el archivo que le explica a la IA, ayúdame con esos ajustes y que lo que ya no sirva siempre d elimine lo que ya no se use para evitar que lea algo que ya no va en la app

## 2. Medición que motiva el cambio (2026-11-25)
Hoy ≈ 64 M de tokens efectivos: generadores 46 %, conversación principal 44 % (≈ 480 000 tokens de contexto releídos por turno, 443 turnos), validadores 5 %, revisores 5 %. Los agentes leen archivos enormes enteros (INVARIANTS 93 KB, TRACEABILITY 50 KB, REQUIREMENTS 36 KB, CONTEXTO 27 KB).

## 3. Alcance
- **T1 (docs/proceso):** `docs/MAPA.md` (mapa corto y vigente: módulos → archivos → INV/CT/UC; «qué leer según la tarea»; comandos), `spec/INDICE.md` (una línea por INV/CT/UC/ADR/BDD con su archivo, para localizar sin leer los archivos grandes; el detalle se lee con `grep -n "^| INV-0xx"`), adelgazar `CONTEXTO_PROYECTO_CLAUDE.md` (quitar historia y lo obsoleto; lo vigente), `work/ESTADO.md` (traspaso de sesión de 20-30 líneas para retomar sin releer nada), archivar las fichas cerradas en `work/archivo/` (no se borran: el historial de git y TRACEABILITY las citan), **enrutamiento de modelos** (Haiku / Sonnet / Opus por complejidad, con criterios) en `docs/PROTOCOLO-AGENTES.md`, `CLAUDE.md` y `.claude/agents/*.md`, y reglas de economía (tareas con lista exacta de archivos a leer, nunca leer enteros INVARIANTS/TRACEABILITY/REQUIREMENTS, máx. 3 agentes en paralelo, avisos agrupados, sesión nueva al cerrar cada cambio grande).
- **T2 (limpieza de código):** eliminar código muerto verificado (backend y frontend): funciones, exports, componentes, archivos, dependencias y constantes sin ninguna referencia, y documentación obsoleta que ya no describe la app; cada borrado con prueba de que no se usa (grep de referencias, imports, rutas, dinámicos) y la suite en verde.
- **Fuera de alcance:** cualquier cambio de comportamiento, spec funcional, SQL, contratos, variables de entorno; `spec/` se conserva (es la fuente de verdad); no se borra historial de BD ni migraciones.

## 4. Plan de tareas
| Tarea | Alcance | Modelo | Estado | Ciclos |
|---|---|---|---|---|
| T1 | Docs/proceso/contexto/enrutamiento de modelos | Sonnet | en curso | 0 |
| T2 | Limpieza de código y docs sin uso | Sonnet | en curso | 0 |
| T3 | Validación: suites y build tras T2 | Haiku/Sonnet | pendiente | 0 |

## 5. Cierre
Pendiente. Despliegue: solo docs/proceso y borrado de código sin uso; push a `main` con aprobación del dueño; sin SQL ni variables nuevas.
