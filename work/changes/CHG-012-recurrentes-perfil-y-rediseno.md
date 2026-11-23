# CHG-012 — Recurrentes, copiar presupuestos, perfil, categorías, avisos y rediseño visual

- **Estado:** listo-para-aprobar (falta el visto bueno del dueño y ejecutar el SQL en Supabase)
- **Fecha:** 2026-11-23 · **Solicitante:** dueño del proyecto
- **Riesgo:** medio (datos nuevos, contraseña y sesión) · modo `completo`

## 1. Pedido original
> Necesito que implementes A1 A3 A4 A5 A6. En las mejoras visuales implementarlas todas

(Propuesta previa: A1 recurrentes, A3 copiar presupuestos, A4 nombre y contraseña en el perfil, A5 página de
categorías, A6 avisos de presupuesto; B1 Inicio más útil, B2 botón «+» en el celular, B3 página pública, B4 modo
oscuro, B5 textos, B6 estados vacíos.)

## 2. Decisiones del dueño (2026-11-23, preguntas en el chat)
| Pregunta | Respuesta |
|---|---|
| ¿Las recurrentes se registran solas o se confirman? | **Pendientes por confirmar** (INV-025) |
| Frecuencias | **Mensual, quincenal y semanal** |
| Cambiar contraseña | **Pedir la actual y cerrar las demás sesiones** (INV-027) |
| Nombre de «Dashboard» | **Inicio** |

Decisiones técnicas propias (dentro de lo aprobado):
- Quincenal = dos días fijos al mes (día ancla y +15), no «cada 14 días»: así cae en las quincenas (15 y 30).
- Se guarda `dia_ancla` para que una recurrente del 31 vuelva al 31 después de febrero.
- Confirmar usa compare-and-set sobre `proxima_fecha` (un doble toque no registra dos veces).
- La contraseña actual incorrecta responde **400** (un 401 haría que el frontend cerrara la sesión) y suma al
  bloqueo del login (5 fallos → 15 min).
- La tabla `recurrentes` nace con RLS activo y sin políticas: solo la usa el backend con `service_role`.

## 3. Spec afectada
REQ-F-006 CA-4, REQ-F-007 CA-4/CA-5, REQ-F-014 CA-2/CA-3, REQ-F-016 (nuevo), alcance en REQUIREMENTS §4;
INV-025, INV-026, INV-027; CT-002 v1.1, CT-005 v1.1, CT-008 (nuevo); UC-012; BDD-RECURRENTES; TRACEABILITY.

## 4. Base de datos (ejecutar ANTES del despliegue)
`backend/sql/2026-11-23_recurrentes.sql` en Supabase → SQL Editor. Solo crea la tabla `recurrentes`; no toca datos.
Se puede repetir. Probado en PostgreSQL 16 local con `backend/sql/pruebas/probar.sh` (también corre en el CI).

## 5. Evidencia
- Backend: `python -m pytest -q` → 216 pruebas pasan (70 nuevas: `test_recurrentes.py`, `test_presupuestos_copia.py`, `test_perfil.py`).
- SQL: `probar.sh` → «OK: migraciones de huérfanos, medio de pago y recurrentes verificadas».
- Frontend: `npx eslint .` 0 problemas · `npm test` 24/24 · `npx next build` correcto.
- Recorrido real con Playwright (backend local con datos de ejemplo): login, Inicio, Recurrentes, Categorías,
  Presupuestos, Perfil y Transacciones en PC e iPhone 13, claro y oscuro; registrar una pendiente con monto
  ajustado; el botón «+» abre Transacciones con el foco en el monto.

## 6. Hallazgo (sin cambiar, requiere decisión: BL-030)
Todos los formularios de la app reciben los montos en pesos (COP, la moneda en que se guardan), aunque la vista se
muestre en otra moneda. Las pendientes siguen la misma regla (proponen el monto en pesos).

## 7. Revisión independiente
**Ciclo 1 (agente `revisor`): BLOQUEADO**, confianza 85 %. Hallazgos y respuesta:
| # | Severidad | Hallazgo | Respuesta |
|---|---|---|---|
| H1 | Bloqueante | Editar o pausar con datos viejos devolvía la próxima fecha a una ocurrencia ya registrada (doble registro) | Corregido: `PUT` con `proxima_fecha` opcional + `proxima_fecha_vista` y compare-and-set; pausar no envía fecha; registrar cierra la edición abierta. Pruebas `test_inv026_editar_con_la_fecha_vieja_no_la_hace_retroceder`, `test_cambiar_la_fecha_exige_haber_visto_la_actual`; recorrido Playwright del escenario |
| H2 | Importante | Si fallaba también la reversión al confirmar, error no controlado y ocurrencia perdida sin aviso | Corregido: reversión protegida; se avisa que la fecha quedó omitida y debe registrarse a mano. Prueba `test_si_tambien_falla_la_reversion_*` |
| H3 | Menor | Tras cambiar la contraseña se releía el usuario; si fallaba, error con la contraseña ya cambiada | Corregido: `update_password` devuelve la versión nueva y el token se firma con ella. Prueba `test_inv027_el_token_nuevo_no_depende_de_volver_a_leer_la_bd` |
| H4 | Menor | Dos copias de presupuestos simultáneas (dos pestañas) pueden duplicar | Aceptado y documentado: requiere una restricción UNIQUE en la BD (BL-031, decisión del dueño) |
| H5 | Menor | Error de pendientes sin «Reintentar» | Corregido: `<ErrorState onRetry>` |

Tras las correcciones: backend 220 pruebas, frontend lint 0, `npm test` 24/24, build correcto.

**Ciclo 2 (agente `revisor`): APROBADO CON OBSERVACIONES**, confianza 88 %. H1-H5 verificados; sin defectos nuevos en el
backend. Observaciones atendidas: aviso cuando la edición recibe 409 (antes el formulario se cerraba sin explicación);
registrar desde pendientes solo cierra la edición de esa misma recurrente y avisa; la edición con cambio de fecha
es una sola escritura condicional (`RecurrenteDB.actualizar(..., esperada=)`); escenario BDD del 409; la prueba de H2
comprueba también el estado final. Resultado: backend 220 pruebas, lint 0, `npm test` 24/24, build correcto.
