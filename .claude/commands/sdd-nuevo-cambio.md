---
description: Inicia un cambio SDD completo (clasificar → spec → plan → implementar → validar → revisar)
argument-hint: <descripción del pedido, tal como lo dijo el cliente>
---

Actúa como el **Coordinador** definido en `.claude/agents/coordinador.md` y sigue `docs/PROTOCOLO-AGENTES.md`.

Pedido original (no lo reinterpretes):

> $ARGUMENTS

Pasos:
1. Crea `work/changes/CHG-NNN-<slug>.md` desde `work/CHANGE-TEMPLATE.md` y registra el pedido literal.
2. Delega en el subagente `clasificador`.
3. Si el clasificador indica `MODO: ligero`, explícame por qué y, salvo que yo diga lo contrario, ejecuta directamente `generador` → `validador`.
4. Si requiere cambio de spec: presenta ambigüedades y preguntas abiertas y **detente hasta que yo apruebe la spec**.
5. Con spec aprobada: divide en tareas pequeñas y ejecuta el bucle `generador` → `validador` → `revisor` por tarea.
6. No hagas `git push` ni toques producción sin mi aprobación explícita.
7. Al terminar, resume: decisiones, archivos, pruebas y resultado, pendientes, y pídeme la aprobación final.
