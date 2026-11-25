# CHG-023 — Panel de administración de usuarios (solo dueño)

- **Estado:** especificación en redacción
- **Fecha:** 2026-11-25 · **Solicitante:** Julián Zúñiga (dueño) · **Riesgo:** alto · **Modo:** completo

## 1. Pedido original (literal, sin reinterpretar)
> ok ahora necesito implementar un panel basico de administracion de usuarios para tener control de toods los que se registran que sea bein compleot. cualquier duda me preguntas.

## 2. Respuestas del dueño (2026-11-25)
- **Acciones:** ver lista y buscar · suspender y reactivar · cerrar sesiones · eliminar cuenta y todos sus datos.
- **Datos por usuario:** básicos (correo, nombre, fecha de registro, estado, moneda) · uso agregado (cantidades; nunca montos ni descripciones) · último acceso.
- **Auditoría:** registro de acciones del administrador.

## 3. Decisiones por defecto del coordinador (provisionales; el dueño puede cambiarlas)
- Acceso igual al Monitor: solo el correo de `OWNER_EMAIL`, 404 para cualquier otro, fail-closed (INV-031).
- El propio dueño no puede suspenderse ni eliminarse desde el panel.
- Suspensión con columna nueva `suspendida` (no reutilizar `is_active`: la limpieza de cuentas sin verificar la borraría).
- `ultimo_acceso` se guarda al iniciar sesión (como máximo una escritura por hora y usuario).
- Auditoría en tabla propia sin datos personales (id del usuario afectado, acción, fecha); sobrevive a la eliminación.
- Eliminar exige escribir el correo del usuario y reutiliza la baja de cuenta existente (REQ-F-013, auth_borrar_de_cuenta, desconexión de WhatsApp).
- Página nueva `/dashboard/usuarios`, visible solo con `es_dueno`.

## 4. Preguntas abiertas
| # | Pregunta | Respuesta |
|---|---|---|

## 5. Spec afectada
_(pendiente de redactar)_ · **Aprobación de la spec:** pendiente

## 6. Plan de tareas
| Tarea | Alcance | Estado |
|---|---|---|

## 7. Registro de ejecución
| Fecha | Agente | Acción | Resultado |
|---|---|---|---|
| 2026-11-25 | coordinador | Pedido y decisiones registrados | CHG creado |

## 8. Cierre
- **Aprobación humana final:** pendiente
