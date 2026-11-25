# CHG-026 — Ejecutor propio y plazo real para `TransaccionDB` (BL-043)

- **Estado:** en-implementación (el dueño aprobó el 2026-11-25: «Ejecutor propio para las transacciones si no es demorado, sí»)
- **Fecha:** 2026-11-25 · **Solicitante:** dueño · **Riesgo:** medio · **Modo:** `estandar` (deuda técnica sin cambio de reglas de negocio; ficha + generador + validador)

## 1. Pedido original (literal)
> Ejecutor propio para las trasnacciones si no es demorado si

## 2. Alcance
Que las operaciones de `TransaccionDB` (crear, actualizar, eliminar y lecturas) dejen de usar el cliente general sin plazo propio y de bloquear el hilo: usan un cliente dedicado con plazo de 4 s y un ejecutor acotado PROPIO (mismo patrón que `models/cuentas.py`: `ThreadPoolExecutor` propio + `BoundedSemaphore` con `acquire(blocking=False)`, 503 genérico inmediato sin encolar, hueco liberado en `add_done_callback`), sin usar los 8 hilos de `auth-estado` (login) ni los 4 de `cuentas`.
- **Fuera de alcance:** reglas de negocio, contratos, esquema SQL, otras tablas (presupuestos, metas, categorías…), el tope por usuario de cuentas (BL-044, el dueño decidió dejarlo libre por ahora).
- **Invariantes a conservar:** INV-001 (dueño en toda operación por id), INV-046..051 (cuentas y saldo: FZ001/FZ002 → 409, 22003 → 422), INV-008, orden `fecha,id` y columnas existentes; errores de BD sin texto crudo ni datos personales en respuestas o logs; modo demo intacto.
- **Comportamiento nuevo visible:** con la BD lenta o el ejecutor lleno, las transacciones responden 503 genérico en 4 s en vez de colgar un hilo; con la BD sana todo igual.

## 3. Pruebas
Ejecutor propio (hilos nombrados, no `auth-estado`, no `cuentas`), 503 sin encolar al saturarlo, hueco liberado en éxito, excepción y cancelación, no-interferencia con login y cuentas, errores FZ→409 y 22003→422 intactos; adaptar SIN DEBILITAR las pruebas existentes con cliente falso (~9 archivos) y justificar cada cambio.

## 4. Plan de tareas
| Tarea | Alcance | Estado | Ciclos |
|---|---|---|---|
| T1 | `models/plataapp.py::TransaccionDB` (+ lo que dependa) y pruebas | en curso | 0 |
| T2 | Validador (ejecuta y mide); trazabilidad y cierre de BL-043 | pendiente | 0 |

## 5. Registro de ejecución
| Fecha | Agente | Acción | Resultado |
|---|---|---|---|
| 2026-11-25 | dueño | Aprueba hacerlo si no es demorado | T1 en curso |

## 6. Cierre
Pendiente. Despliegue: push a `main` con aprobación del dueño; sin SQL ni variables nuevas.
