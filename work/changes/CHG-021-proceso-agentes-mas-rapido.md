# CHG-021 — Proceso de agentes más rápido y barato

- **Estado:** aplicado (rama de trabajo; pendiente de aprobación para `main`)
- **Fecha:** 2026-11-24 · **Solicitante:** Julián Zúñiga (dueño) · **Riesgo:** bajo (solo proceso; sin código de la app)

## 1. Pedido original (literal)
> Necesito mejorar esas skill ya que se está demorando demasiado en realizar cambios en la aplicación. Dime qué se puede mejorar y aplicar a esa skill actuales o la forma de trabajar con los agentes. [...] Sí, aplica todos. Esos cambios con el objetivo de mejorar tiempos y no gastar tantos tokens

## 2. Diagnóstico (datos de CHG-017 a CHG-020)
- El Monitor usó 31 agentes y ~3,1 millones de tokens; las 3 especificaciones nuevas, ~1,2 millones antes de escribir código.
- Validador y revisor repetían la misma suite y releían los mismos archivos; las rondas de corrección repetían tipos de hallazgo (plazos de BD, bcrypt en el hilo principal, referencias de prueba obsoletas, documentación desactualizada).
- Agentes de 15-25 min sin avisos; un reinicio del contenedor perdió trabajo sin guardar.

## 3. Cambios aplicados
1. Tres modos (`rapido`, `estandar`, `completo`); `rapido` sin clasificador ni revisor.
2. Especificación proporcional: una ficha por cambio como fuente única; CT/ADR/UC/BDD solo cuando cambian un contrato público, una decisión de arquitectura o un flujo de usuario; validación de spec en una sola pasada.
3. Validador = ejecuta y mide; revisor = lee y razona, en paralelo, sin repetir la suite.
4. Lista de comprobación previa del generador con los hallazgos recurrentes.
5. Un ciclo de corrección completo y uno de verificación acotada; máximo 2 ciclos (antes 3).
6. Tareas de ~10 minutos, guardado en la rama al terminar cada una, informes cortos.
7. Paralelismo de tareas de archivos distintos.
**No se recorta:** la revisión independiente en autenticación, dinero, datos personales, migraciones y seguridad; ni la aprobación humana ni el push a `main`.

## 4. Archivos
`CLAUDE.md`, `docs/PROTOCOLO-AGENTES.md`, `docs/CICLO-SDD.md`, `.claude/commands/sdd-nuevo-cambio.md`, `.claude/agents/{clasificador,coordinador,generador,validador,revisor}.md`.

## 5. Cierre
- **Aprobación humana final:** pendiente de subir a `main`.
