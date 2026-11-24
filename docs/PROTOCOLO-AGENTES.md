# Protocolo entre agentes

## Flujo

```
Persona ──pedido──▶ COORDINADOR ──▶ CLASIFICADOR
                        │                 │ tipo / riesgo / flujo
                        ◀─────────────────┘
          (spec aprobada por la persona)
                        │
              ┌─────────▼─────────┐
              │ por cada tarea:   │
              │ GENERADOR         │
              │    ▼              │
              │ VALIDADOR ──✘──┐  │   rechazo → vuelve al generador
              │    ▼ ✔         │  │   con observaciones concretas
              │ REVISOR ───✘───┘  │
              └─────────┬─────────┘
                        ▼ ✔
                  Persona aprueba
```

## Modo proporcional (Finanzy) — tres modos

Finanzy es una app personal con un solo desarrollador: el esfuerzo se reparte según el daño posible (CHG-021: menos tiempo y menos tokens sin quitar controles donde importan).

| Modo | Cuándo | Flujo |
|---|---|---|
| `rapido` | Riesgo **bajo**: textos, estilos, accesibilidad, una tarjeta o campo nuevo en pantalla, documentación; sin lógica de negocio, datos, dinero ni seguridad | **Sin clasificador** (el coordinador lo decide con esta tabla) → un generador (con pruebas) → el coordinador corre la suite **una vez** → aprobación |
| `estandar` | Riesgo **medio**: funcionalidad o cambio de comportamiento que **no** toca autenticación, dinero, datos personales, migraciones ni cabeceras | Clasificador → **ficha de cambio** aprobada por la persona → generador → validador (ejecuta y mide) → aprobación. El revisor solo si el validador marca algo dudoso o la persona lo pide |
| `completo` | Riesgo **alto**: autenticación/sesiones, dinero, datos personales o exportación de datos, migraciones SQL, límites/seguridad, contratos públicos | Clasificador → ficha + documentos de diseño necesarios → validación de la spec (una pasada) → aprobación → generador → validador **y** revisor en paralelo → aprobación |

El coordinador (o el clasificador) propone el modo; ante la duda entre dos, se usa el más estricto. La persona puede pedir siempre un modo más estricto. **La revisión independiente en cambios de dinero, autenticación y datos personales no se recorta.**

## Reparto de trabajo (para no repetir ni gastar de más)
- **Validador = ejecuta y mide**: suite, auditoría de dependencias, pruebas contra PostgreSQL real, scripts activos de abuso. Entrega la evidencia (comandos y salidas) para que el revisor la reutilice.
- **Revisor = lee y razona**: diff contra la spec, seguridad, regresiones, calidad de las pruebas. **No vuelve a correr la suite completa**: usa la evidencia del validador y ejecuta solo lo puntual que necesite para comprobar un hallazgo.
- **La suite completa se corre una vez por etapa.** Tres pasadas seguidas solo cuando haya concurrencia, tiempos o sospecha de pruebas intermitentes; si no, una pasada completa más una repetición de las pruebas nuevas.
- Validador y revisor corren **en paralelo**, no uno tras otro.

## Ciclos de corrección
- **Primer ciclo: corrección completa** de los hallazgos. **Segundo ciclo: verificación acotada**: el validador/revisor comprueban solo los hallazgos corregidos y el diff nuevo, no vuelven a auditar todo.
- Máximo **2 ciclos**; si queda un bloqueante, se escala a la persona con un resumen (antes eran 3).
- Antes de escribir, el generador aplica la **lista de comprobación previa** (abajo): evita repetir los hallazgos más comunes.

## Lista de comprobación previa del generador (hallazgos que se repiten)
1. Toda llamada a la base de datos o a un servicio externo tiene **plazo real** (no solo `wait_for` sobre un hilo) y falla de forma segura.
2. El trabajo pesado (bcrypt, generación de archivos, lecturas grandes) va **fuera del hilo principal**, con un ejecutor acotado que responde 503 sin encolar.
3. Todo estado de seguridad (bloqueos, códigos, límites) vive en la base y es **atómico**; el modo en memoria solo fuera de producción.
4. Nada de datos personales ni de excepciones completas en logs.
5. Las tablas que reciben datos de usuarios tienen **retención y tope de crecimiento**.
6. Cada prueba que la spec nombra **existe con ese nombre**; si se renombra, se actualiza en la spec en el mismo cambio.
7. Spec, trazabilidad y notas de despliegue (SQL antes que el backend) actualizadas en el mismo cambio.
8. Las pruebas de concurrencia o de SQL se escriben contra PostgreSQL real, no solo con un simulado.

## Tareas pequeñas y avisos
- Cada tarea de generación debe caber en **unos 10 minutos y un alcance** (un archivo grande o una capa). Si es mayor, el coordinador la divide.
- **Al terminar cada tarea se guarda en la rama** (commit y push a la rama de trabajo, nunca a `main`) para que un reinicio del entorno no pierda trabajo.
- Los agentes devuelven un informe **corto**: máximo ~40 líneas (generador y validador) o ~60 (revisor), solo lo que el coordinador necesita para decidir.
- Tareas de **archivos distintos** (servidor y frontend de un mismo cambio, o cambios independientes) pueden correr **en paralelo**.

## Especificación proporcional
- **Una ficha por cambio** (`work/changes/CHG-*.md`): pedido, REQ con criterios, invariantes afectadas, **pruebas nombradas**, decisiones y plan. Es la **fuente única**: `TRACEABILITY.md` solo la referencia.
- Se crean documentos aparte solo cuando hacen falta: **contrato (CT)** si cambia una API pública, **ADR** si hay una decisión de arquitectura o una librería nueva, **UC/BDD** si hay un flujo de usuario nuevo y no trivial. No se duplican los nombres de prueba en cada documento.
- La validación de la spec es **una sola pasada**; solo se repite si hubo bloqueantes.

## Contrato de entrega (todos los agentes)
Cada agente termina con su bloque de salida de formato fijo (ver su perfil) que incluye **estado/veredicto** y **confianza 0-100 %**.

## Reglas de escalado a humano
- Confianza de cualquier agente < umbral (CLAUDE.md, 85 % por defecto).
- Más de N ciclos de rechazo en la misma tarea (2 por defecto; ver «Ciclos de corrección»).
- Ambigüedad o contradicción en la spec; cambio de regla de negocio.
- Riesgo ALTO (permisos, datos personales, dinero, contratos públicos, migraciones de datos).
- Acciones destructivas o relacionadas con producción.

## Separación de poderes
| Quien | Puede | No puede |
|---|---|---|
| Coordinador | Orquestar, escribir en `work/`, registrar spec aprobada | Escribir código, decidir reglas |
| Clasificador | Leer, clasificar | Escribir, proponer soluciones |
| Generador | Escribir código/pruebas | Cambiar spec, aprobarse |
| Validador | Ejecutar pruebas, bloquear | Modificar código |
| Revisor | Auditar (lectura) | Modificar, aprobar sin evidencia |

Un agente nunca es la única evidencia de calidad: las reglas críticas se comprueban con pruebas deterministas.

## Contexto mínimo
Pasar a cada agente: la tarea + rutas de los archivos de spec relevantes. No pegar documentos enteros. No cargar MCP ni herramientas innecesarias.

## Modelos (estrategia costo/calidad, ajustar a lo disponible con `/model`)
| Agente | Modelo | Razón |
|---|---|---|
| Coordinador, Revisor | opus | Razonamiento, planificación, revisión independiente |
| Generador, Validador | sonnet | Implementación y pruebas con criterios claros |
| Clasificador | haiku | Tarea simple y rápida (en modo `rapido` no se usa) |

Para ahorrar tokens: los agentes que solo redactan o corrigen documentos de spec usan `sonnet`; el `opus` se reserva para el coordinador y el revisor de cambios de riesgo alto.

Cambiar el modelo = editar la línea `model:` del perfil en `.claude/agents/`.

## Auditoría
Cada archivo `work/changes/CHG-*.md` registra: qué agente hizo qué, herramientas relevantes, pruebas ejecutadas y decisiones humanas.
