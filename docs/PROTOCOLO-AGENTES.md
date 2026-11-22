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

## Modo proporcional (Finanzy)

Finanzy es una app personal con un solo desarrollador: el ciclo completo se reserva para lo que puede causar daño.

| Modo | Cuándo | Flujo |
|---|---|---|
| `completo` | Riesgo medio o alto, o cualquier cambio de comportamiento, contrato, datos o seguridad | Clasificador → spec aprobada por la persona → generador → validador → revisor → aprobación |
| `ligero` | Riesgo bajo: textos, estilos, accesibilidad, documentación, sin cambiar lógica ni datos | Clasificador → generador → validador → aprobación |

El clasificador propone el modo; ante la duda se usa `completo`. La persona puede pedir siempre el modo completo.

## Contrato de entrega (todos los agentes)
Cada agente termina con su bloque de salida de formato fijo (ver su perfil) que incluye **estado/veredicto** y **confianza 0-100 %**.

## Reglas de escalado a humano
- Confianza de cualquier agente < umbral (CLAUDE.md, 85 % por defecto).
- Más de N ciclos de rechazo en la misma tarea (3 por defecto).
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
| Clasificador | haiku | Tarea simple y rápida |

Cambiar el modelo = editar la línea `model:` del perfil en `.claude/agents/`.

## Auditoría
Cada archivo `work/changes/CHG-*.md` registra: qué agente hizo qué, herramientas relevantes, pruebas ejecutadas y decisiones humanas.
