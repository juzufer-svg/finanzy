# Ciclo SDD con puertas de control

> En Finanzy hay tres modos (ver `PROTOCOLO-AGENTES.md`):
> - **`rapido`** (riesgo bajo): etapas 1, 8 y 11 (el coordinador corre la suite una vez).
> - **`estandar`** (riesgo medio): etapas 1-4, 8, 9 y 11, con una **ficha de cambio** como especificación; revisor solo si hay dudas.
> - **`completo`** (riesgo alto: autenticación, dinero, datos personales, migraciones, seguridad): todas las etapas; validador y revisor en paralelo.

**Modelos por etapa** (parámetro `model`; detalle en `PROTOCOLO-AGENTES.md`): clasificación, documentación y suites → haiku; generación, validación y coordinación → sonnet; revisión `completo` de dinero/seguridad/migraciones y diseño con concurrencia → opus.

El flujo es iterativo: si una prueba revela una ambigüedad o cambia un requerimiento, se vuelve a la especificación, se aprueba y se repite el ciclo afectado.

| # | Etapa | Responsable | Entregable | Puerta (no avanzar sin…) |
|---|---|---|---|---|
| 1 | Recepción | Coordinador | Pedido literal en `work/changes/CHG-*.md` | Pedido registrado sin reinterpretar |
| 2 | Clasificación | Clasificador | Tipo, riesgo, flujo, preguntas | Confianza ≥ umbral o decisión humana |
| 3 | Análisis | Coordinador + persona | Alcance, actores, reglas, restricciones, riesgos, preguntas abiertas | Preguntas críticas respondidas |
| 4 | Especificación | Persona (aprueba) | REQ con id y criterios de aceptación | **Aprobación humana de la spec** |
| 5 | Diseño | Persona + Coordinador | Dominio, estados, invariantes, UC, flujos, contratos, BDD, ADR | Coherente con REQ |
| 6 | Validación de spec | `/sdd-validar-spec` | Informe de coherencia (**una sola pasada**) | Sin hallazgos bloqueantes |
| 7 | Coordinación | Coordinador | Tareas pequeñas con dependencias | Cada tarea: un alcance, criterios verificables |
| 8 | Generación | Generador | Código + pruebas + trazabilidad | Pruebas escritas y pasando localmente |
| 9 | Validación técnica | Validador (ejecuta y mide) | Veredicto con evidencia reutilizable | `APROBADO` |
| 10 | Revisión | Revisor (lee y razona; **en paralelo** con la 9; no repite la suite) | Veredicto contra spec | `APROBADO` (o escalado tras 2 ciclos) |
| 11 | Aprobación y entrega | Persona | Trazabilidad, docs, notas de versión | **Aprobación humana** |

## Definition of Done (checklist antes de aceptar un cambio)

- [ ] El requerimiento tiene identificador, alcance y criterios de aceptación.
- [ ] Se actualizaron reglas, estados y contratos afectados.
- [ ] El cambio respeta invariantes y permisos.
- [ ] Hay pruebas unitarias, de integración o aceptación apropiadas.
- [ ] Las pruebas se ejecutaron y hay evidencia guardada en el archivo del cambio.
- [ ] El revisor comprobó el cambio contra la spec.
- [ ] Trazabilidad y documentación actualizadas.
- [ ] Aprobación humana cuando corresponde (riesgo medio/alto siempre).

## Cuándo se vuelve a la spec
Ambigüedad descubierta · contradicción spec/código · cambio de regla pedido por el cliente · prueba imposible de escribir por criterio vago.
