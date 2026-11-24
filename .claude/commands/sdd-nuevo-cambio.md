---
description: Inicia un cambio SDD (modo rápido, estándar o completo según el riesgo)
argument-hint: <descripción del pedido, tal como lo dijo el cliente>
---

Actúa como el **Coordinador** definido en `.claude/agents/coordinador.md` y sigue `docs/PROTOCOLO-AGENTES.md`.

Pedido original (no lo reinterpretes):

> $ARGUMENTS

Pasos:
1. Crea `work/changes/CHG-NNN-<slug>.md` desde `work/CHANGE-TEMPLATE.md` y registra el pedido literal.
2. Elige el modo con la tabla de `docs/PROTOCOLO-AGENTES.md`: `rapido` (riesgo bajo; **sin clasificador**), `estandar` (riesgo medio) o `completo` (riesgo alto). Ante la duda entre dos, el más estricto. Dime el modo elegido y por qué en una línea. Si no es `rapido`, delega en `clasificador`.
3. `rapido`: un `generador` con pruebas, tú corres la suite una vez y me pides la aprobación.
4. `estandar` / `completo`: si cambia comportamiento, redacta una **ficha de cambio** corta en `work/changes/CHG-NNN` (REQ y criterios, invariantes afectadas, pruebas nombradas, plan de tareas); crea CT/ADR/UC/BDD solo si de verdad cambian un contrato público, una decisión de arquitectura o un flujo de usuario. Presenta preguntas abiertas y **detente hasta que yo apruebe la ficha**.
5. Con la ficha aprobada: divide en tareas de **~10 minutos y un solo alcance**, con la lista de comprobación previa del protocolo; tareas de archivos distintos pueden ir **en paralelo**. Al terminar cada tarea, guarda en la rama de trabajo (commit y push a la rama, nunca a `main`).
6. Verificación: `estandar` → `validador` (ejecuta y mide). `completo` → `validador` **y** `revisor` **en paralelo** (el revisor no repite la suite). Máximo **2 ciclos**: el segundo solo verifica lo corregido.
7. No hagas `git push` a `main` ni toques producción sin mi aprobación explícita.
8. Al terminar, resume en pocas líneas: decisiones, archivos, pruebas y resultado, pendientes, y pídeme la aprobación final.
