# CHG-001 — Cerrar sesiones al cambiar la contraseña

- **Estado:** listo-para-aprobar
- **Fecha:** 2026-11-22 · **Solicitante:** dueño del proyecto
- **Riesgo:** alto (seguridad, base de datos, contrato de sesión)

## 1. Pedido original (literal, sin reinterpretar)
> Pendiente 2 de la sección 11 del contexto: cerrar sesiones al cambiar la contraseña (BL-003, pregunta abierta 4).

## 2. Clasificación
Cambio de regla · módulo autenticación · REQ-F-003 · modo `completo`.

## 3. Análisis
- **Alcance:** al restablecer la contraseña (`POST /auth/reset-password`) se invalidan todos los JWT emitidos antes.
  También el cambio manual por SQL documentado en el contexto §5 (suma 1 a `session_version`).
- **Fuera de alcance:** no existe un endpoint de "cambiar contraseña" con sesión iniciada; botón "cerrar sesión en
  todos los dispositivos"; aviso en el frontend (el 401 ya lleva al login).
- **Diseño:** columna `users.session_version integer not null default 0`; claim `sv` en el JWT; `api/sesion.py`
  (`usuario_de_sesion`) valida en toda ruta protegida (`users.py` y `plataapp.py`).
- **Compatibilidad:** tokens sin `sv` valen como 0 → nadie pierde la sesión al desplegar.
- **Riesgos:** una consulta corta extra a Supabase por petición. Si Supabase falla → 503 (no 401, para no cerrar la
  sesión por un fallo pasajero). Si se despliega sin la columna, todas las rutas protegidas responden 503:
  **la migración va antes del push**.
- **Solape con el PR #2 (borrador):** también vuelve asíncrono `get_user_id` y consulta el usuario en cada ruta. Las
  líneas `usuario_id = await get_user_id(authorization)` quedaron idénticas a las del PR #2 para reducir conflictos;
  el cuerpo de `get_user_id` y `users.py` sí chocarán y deberá resolverse al retomarlo.

## 4. Preguntas abiertas
| # | Pregunta | Impacto | Respuesta | Quién |
|---|---|---|---|---|
| 1 | ¿Cerrar sesiones al cambiar la contraseña? | REQ-F-003 | Sí | Dueño, 2026-11-22 |

## 5. Spec afectada
- REQ: REQ-F-003 (CA-4) · UC: UC-003 · Invariantes: INV-016 (nuevo) · Contratos: CT-001, CT-002 (errores comunes
  401/503), CT-003…006 (permiso) · BDD: BDD-RECUPERACION · ADR: ADR-003 (pendiente resuelto)
- **Aprobación de la spec:** dueño, 2026-11-22 (aprobó implementar el pendiente 2)

## 6. Plan de tareas
| Tarea | Alcance | Depende de | Estado | Ciclos |
|---|---|---|---|---|
| T1 | Migración SQL `backend/sql/2026-11-22_session_version.sql` | — | Hecho | 0 |
| T2 | Modelo, `api/sesion.py`, rutas, claim `sv` | T1 | Hecho | 0 |
| T3 | Pruebas `tests/test_sesiones.py` | T2 | Hecho | 0 |
| T4 | Spec, trazabilidad, contexto | T2 | Hecho | 0 |

## 7. Registro de ejecución
| Fecha | Agente | Acción | Resultado / evidencia |
|---|---|---|---|
| 2026-11-22 | Claude | Implementación y pruebas | `python -m pytest -q` → 64 pasan; las nuevas fallan sin el cambio |

## 8. Cierre
- Archivos: ver el PR.
- Pendientes: ejecutar la migración en Supabase, aprobación humana y push a `main`.
- **Aprobación humana final:** pendiente

## 9. Revisión independiente (agente revisor, confianza 88 %)
Aprobado con observaciones, todas atendidas: incremento de versión con actualización condicional y reintento
(antes leía y escribía sin control de concurrencia); prueba de `sv` en `verify-email`; el log de errores de
Supabase solo registra el tipo de error.
