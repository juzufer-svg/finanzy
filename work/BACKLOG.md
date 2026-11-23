# Backlog y cambios en curso

Lo mantiene el Coordinador. Detalle de cada cambio en `work/changes/CHG-NNN-slug.md`.
Para empezar cualquiera: `/sdd-nuevo-cambio <título o descripción>`.

| ID | Título | Tipo | Riesgo | Estado | Origen |
|---|---|---|---|---|---|
| BL-001 | Evitar la pausa de Supabase por inactividad (tarea programada en GitHub Actions) | nueva-funcionalidad | medio | Hecho (PR #3) | REQ-N-007 |
| BL-002 | Respaldo semanal automático de la base de datos + prueba de restauración | nueva-funcionalidad | alto | Hecho (PR #3) | REQ-N-008 |
| BL-003 | Cerrar las sesiones abiertas al cambiar la contraseña (versión de sesión por usuario) | cambio-de-regla | alto | Hecho (CHG-001, PR #4) | Pregunta abierta 4 |
| BL-004 | CI en GitHub Actions: pytest + pip-audit del backend, lint + build del frontend en cada push | deuda-tecnica | medio | Hecho (CHG-002, PR #5) | REQ-N-009 |
| BL-005 | Revisar RLS de Supabase con Security Advisor | deuda-tecnica | medio | Pendiente | Contexto §11 |
| BL-006 | Unificar la longitud mínima de contraseña (registro 6 vs. recuperación 8) | cambio-de-regla | medio | Hecho (CHG-002, PR #5) | Pregunta abierta 1 |
| BL-007 | Gasto diario promedio con los días reales del mes | correccion-de-bug | bajo | En revisión (CHG-006) | Pregunta abierta 2 |
| BL-008 | Decidir el uso o eliminación de la columna `metas.estado` | deuda-tecnica | medio | Pendiente | Pregunta abierta 3 |
| BL-009 | Limpiar los documentos antiguos de la raíz (`API_REFERENCE.md`, `ARCHITECTURE.md`, `QUICKSTART.md`, `START_HERE.md`, `*.sh`, …) y actualizar `README.md` | deuda-tecnica | bajo | En revisión (CHG-005) | ADR-004 |
| BL-010 | Pruebas automatizadas del frontend (avance de presupuestos, reportes, moneda) | deuda-tecnica | medio | En curso: reportes y buscador con `npm test` (CHG-006); faltan presupuestos y moneda | TRACEABILITY (huérfanos) |
| BL-011 | Quitar de la lista de CORS los dominios viejos `plataapp*.vercel.app` | deuda-tecnica | bajo | Hecho (CHG-002, PR #5) | `backend/app/main.py` |
| BL-012 | Sesión en cookie HttpOnly + proxy de Next.js + CSRF (quitar el token de `localStorage`) | seguridad | alto | Hecho (CHG-003, PR #6) | Revisión PR #2, prioridad 1 |
| BL-013 | Abono a metas atómico (función SQL/RPC: sumar y registrar el gasto en una sola transacción) | correccion-de-bug | alto | En revisión (CHG-004) | Revisión PR #2, prioridad 3 |
| BL-014 | Códigos, límites y bloqueos de login persistentes en PostgreSQL (sobreviven reinicios) | seguridad | medio | Pendiente | Revisión PR #2, prioridad 2 |
| BL-015 | Verificar en Supabase las llaves foráneas `ON DELETE CASCADE` y conciliar los 64 registros huérfanos y `presupuestos.mes_año` NULL (solo con decisión del dueño) | datos | alto | En revisión (CHG-005; SQL listo, lo ejecuta el dueño) | Revisión PR #2 |
| BL-016 | Cerrar el PR #2 (sus partes útiles pasaron a CHG-002) | deuda-tecnica | bajo | Pendiente (requiere el visto bueno del dueño) | Revisión PR #2 |
| BL-017 | Alinear el tope de montos (1e12) con `NUMERIC(12,2)` y limitar a 2 decimales | correccion-de-bug | medio | Pendiente | Revisión CHG-004 |
| BL-018 | Medio de pago en las transacciones (Débito, Crédito, Efectivo, Transferencia, Nequi / Daviplata) | nueva-funcionalidad | medio | En revisión (CHG-007; SQL antes del despliegue) | Pedido del dueño 2026-11-22 |
| BL-019 | Decidir si se borra la columna sin uso `presupuestos."mes_año"` (2 filas NULL; el código usa `mes_ano`) | datos | bajo | Pendiente (decisión del dueño) | CHG-005 |
| BL-020 | Diseño profesional y responsive en PC y iPhone (logo duplicado, mes en mayúsculas, zona segura, botones táctiles) | mejora | bajo | Hecho (CHG-008, PR #10) | Pedido del dueño 2026-11-22 |
| BL-021 | Filtro de período compartido por todas las pestañas y rediseñado (se mantiene al navegar y recargar) | mejora | bajo | Hecho (CHG-009, PR #11) | Pedido del dueño 2026-11-22 |
| BL-022 | Decidir si la nueva transacción propone una fecha del mes que se está viendo | mejora | bajo | Descartado: el dueño decidió (2026-11-22) que siga proponiendo hoy; la fecha se elige en el campo Fecha | CHG-009 |
| BL-023 | Asistente con Claude para preguntar por las finanzas en lenguaje natural (tool use, solo lectura, Haiku) | nueva-funcionalidad | medio | En revisión (CHG-010; requiere `ANTHROPIC_API_KEY` en Railway y saldo en la Claude Console) | Pedido del dueño 2026-11-22 |
| BL-024 | Menú «Asistente IA» y, en el celular, que el menú lateral no reaparezca solo al abrir el asistente | mejora | bajo | En revisión (CHG-011) | Pedido del dueño 2026-11-22 |
| BL-025 | Transacciones recurrentes que se proponen y se confirman (mensual, quincenal, semanal) | nueva-funcionalidad | medio | En revisión (CHG-012; SQL `2026-11-23_recurrentes.sql` antes del despliegue) | Pedido del dueño 2026-11-23 (A1) |
| BL-026 | Copiar los presupuestos del mes anterior | mejora | bajo | En revisión (CHG-012) | Pedido del dueño 2026-11-23 (A3) |
| BL-027 | Editar el nombre y cambiar la contraseña desde el perfil | seguridad | medio | En revisión (CHG-012) | Pedido del dueño 2026-11-23 (A4) |
| BL-028 | Página propia de Categorías y avisos de presupuesto en el Inicio | mejora | bajo | En revisión (CHG-012) | Pedido del dueño 2026-11-23 (A5, A6) |
| BL-029 | Rediseño visual: Inicio, botón «+» en el celular, página pública, modo oscuro, textos y estados vacíos | mejora | bajo | En revisión (CHG-012) | Pedido del dueño 2026-11-23 (B1-B6) |
| BL-030 | Decidir si los formularios piden los montos en la moneda que se está viendo (hoy siempre en pesos COP, aunque se muestre en US$) | mejora | medio | Pendiente (decisión del dueño) | Hallazgo de CHG-012 |
