# CHG-029 — Alinear el tope de montos con `NUMERIC(12,2)` (BL-017)

- **Estado:** listo-para-aprobar
- **Fecha:** 2026-11-25 · **Solicitante:** dueño
- **Riesgo:** alto · **Modo:** completo (dinero e invariante crítica)

## 1. Pedido original (literal, sin reinterpretar)
> BL-017: alinear el tope de montos con NUMERIC(12,2): máximo 9 999 999 999,99 y 2 decimales (INV-003). Autorizado por el dueño el 2026-11-25. Modo completo.

## 2. Clasificación
Cambio de regla · riesgo alto · modo completo · confianza 80 % (clasificador).

## 3. Análisis
- **Alcance:** transacciones (con y sin cuenta), presupuestos, metas (objetivo, ahorrado, abono), recurrentes (plantilla y confirmar), WhatsApp y migración SQL (`transacciones.monto`, `presupuestos.limite_mensual`, `metas.monto_objetivo` y `metas.monto_actual` a `NUMERIC(12,2)`).
- **Fuera de alcance:** modificar datos existentes; cuentas y transferencias (ya cumplen INV-051; `saldo_inicial`, `transferencias.monto` y `recurrentes.monto` ya son `NUMERIC(12,2)`).
- **Corrección (2026-11-25):** la premisa «todas las columnas ya son `NUMERIC(12,2)`» era falsa. Verificado en producción (solo lectura): las 4 columnas citadas arriba son `numeric` sin precisión; 0 filas sobre 9 999 999 999,99 y 0 con más de 2 decimales (84/1/2 filas).
- **Orden de despliegue:** 1) `backend/sql/2026-11-25_montos_numeric_12_2_diagnostico.sql` (solo lectura); 2) `backend/sql/2026-11-25_montos_numeric_12_2.sql` en el SQL Editor y revisar su comprobación; 3) push a `main`. La migración es compatible con el backend actual.
- **Actores y permisos:** sin cambios.
- **Reglas:** endurece INV-003 (no la debilita: no exige ADR nuevo).
- **Riesgos:**
  - El navegador ya redondea a 2 decimales al convertir de moneda (`fromInputValue`): no se rompen otras monedas.
  - Varios montos son `float` y se suman entre sí: validar con `Decimal` sin cambiar el tipo que usan rutas y modelos.
  - Un abono puede dejar `monto_actual` por encima del tope aunque el abono sea válido.

### Criterios de aceptación
1. Un monto > 9 999 999 999,99 responde 422 en todas las entradas de la API del alcance.
2. Un monto con más de 2 decimales responde 422 en esas mismas entradas.
3. 9 999 999 999,99 y 0,01 se aceptan; siguen rigiendo > 0 y ahorrado ≥ 0.
4. Un abono cuyo acumulado supere el tope responde 422 y no cambia nada (ni gasto, ni meta, ni cuenta).
5. WhatsApp no registra montos por encima del tope (ver P1 para los decimales).
6. La pantalla muestra un mensaje claro (ver P2).

## 4. Preguntas abiertas
| # | Pregunta | Impacto | Respuesta | Quién |
|---|---|---|---|---|
| P1 | WhatsApp con más de 2 decimales: ¿redondear como hoy (recomendado) o rechazar? | `utils/whatsapp.py` | Redondear como hoy | dueño, 2026-11-25 |
| P2 | ¿Mostrar «El monto debe tener máximo 2 decimales y no superar $9.999.999.999,99 (pesos colombianos)» (recomendado) o dejar «Revisa los datos ingresados.»? | esquemas y `lib/api-error.ts` | Mensaje claro | dueño, 2026-11-25 |

## 5. Spec afectada
- INV-003 (texto y prueba), INV-051 (quitar la nota sobre BL-017), `spec/INDICE.md`, `spec/TRACEABILITY.md`
- Contratos: CT-003, CT-005, CT-006, CT-008, CT-009
- ADR-009: nota de que BL-017 quedó resuelto · REQ/UC/BDD: sin cambios
- **Aprobación de la spec:** dueño, 2026-11-25

## 6. Plan de tareas
| Tarea | Alcance | Depende de | Estado | Ciclos |
|---|---|---|---|---|
| T1 | Spec: INV, contratos, índice | aprobación | pendiente | 0 |
| T2 | `schemas/plataapp.py` (tope único), acumulado del abono en rutas; pruebas `test_inv003_tope_en_cada_entrada`, `test_inv003_maximo_dos_decimales`, `test_inv003_limites_aceptados`, `test_inv003_abono_acumulado_422_sin_cambios` | T1 | pendiente | 0 |
| T3 | `utils/whatsapp.py`; prueba `test_inv003_whatsapp_respeta_tope` | T2 | pendiente | 0 |
| T4 | `frontend/lib/api-error.ts` y su prueba (según P2) | T1 | pendiente | 0 |
| T6 | Migración SQL, diagnóstico y pruebas en PostgreSQL local | H1 | hecha (sin aplicar en Supabase) | 1 |
| T5 | Trazabilidad, `BACKLOG.md`, `ESTADO.md` | T2-T4 | pendiente | 0 |

## 7. Registro de ejecución
| Fecha | Agente | Acción | Resultado / evidencia |
|---|---|---|---|
| 2026-11-25 | clasificador | Clasificar | riesgo alto, modo completo |
| 2026-11-25 | coordinador | Ficha | aprobada por el dueño |
| 2026-11-25 | generador | T2-T4 | commit 8f1504e |
| 2026-11-25 | revisor | Revisión | aprobado, observaciones menores |
| 2026-11-25 | validador | Validación | bloqueado (H1): confirmar precisión de las columnas de montos en Supabase; `backend/sql/pruebas/01_base_como_produccion.sql` declara `numeric` sin precisión en `metas` |
| 2026-11-25 | generador | T6 (resuelve H1 en el repo) | `probar.sh` completo en PostgreSQL 16 local: OK; reversión probada a mano; base de prueba corregida (`numeric` sin precisión) y aserción de `08_comprobar_cuentas.sql` sobre el tope en `transacciones` movida tras la migración. pytest: 2 fallos en `test_exportar.py` (sin cambios de Python en esta tarea). Pendiente: validar y que el dueño ejecute el SQL |
| 2026-11-25 | validador y revisor | Ciclo 2 (migración) | aprobados |

## 8. Cierre
- Decisiones:
- Archivos modificados:
- Pruebas ejecutadas y resultado:
- Pendientes:
- **Aprobación humana final:**
