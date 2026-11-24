# Requisitos no funcionales (medibles)

| ID | Categoría | Requisito | Valor objetivo | Cómo se mide / prueba | Estado |
|---|---|---|---|---|---|
| REQ-N-001 | Seguridad | Aislamiento de datos entre usuarios | 100 % de operaciones por ID verifican al propietario del registro | `tests/test_propiedad.py` (INV-001, INV-002) | Cumple |
| REQ-N-002 | Seguridad | Fuerza bruta y abuso de correo limitados | Límites de INV-010 | `tests/test_limites.py`, `tests/test_auth.py` | Cumple |
| REQ-N-003 | Seguridad | Sin secretos en código, logs ni frontend; sin endpoints de diagnóstico, **salvo el Monitor del Dueño (REQ-F-018), que no lo es: solo responde al Dueño, a los demás 404 fail-closed, solo lectura y sin exponer secretos (INV-031 a INV-033)**; cabeceras de seguridad (CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, HSTS) | 0 secretos; cabeceras presentes en todas las rutas | `tests/test_app_seguridad.py`, `tests/test_correo.py`, `tests/test_monitor.py`; `curl -I https://finanzyapp.vercel.app` | Cumple (Monitor: por implementar) |
| REQ-N-011 | Seguridad / Monitor | Timeout de consulta a cada plataforma (INV-034) | 5 s por plataforma; una plataforma lenta no retrasa más de 5 s ni afecta a las demás | `tests/test_monitor.py::test_inv034_timeout_de_5s_marca_no_disponible` | Por implementar (CHG-017) |
| REQ-N-012 | Seguridad / Monitor | Caché de las consultas externas (INV-035) | 60 s por plataforma | `tests/test_monitor.py::test_inv035_cache_60s_no_reconsulta` | Por implementar (CHG-017) |
| REQ-N-013 | Seguridad / Monitor | Límite de frecuencia por Dueño (INV-035) | 20 peticiones/min; la 21.ª responde 429 | `tests/test_monitor.py::test_inv035_limite_20_por_minuto_responde_429` | Por implementar (CHG-017) |
| REQ-N-014 | Datos / Monitor | Retención de los contadores diarios (INV-036) | 90 días; purga oportunista al escribir, como mucho una vez al día | `tests/test_monitor.py::test_inv036_purga_a_90_dias_una_vez_al_dia` | Por implementar (CHG-017) |
| REQ-N-015 | Rendimiento / Monitor | Tiempo de respuesta de `GET /monitor/resumen` | p95 < 3 s con la caché caliente (60 s); en frío, como máximo ≈ 5 s (plataformas en paralelo con timeout de 5 s) | Prueba de tiempos con plataformas simuladas en `tests/test_monitor.py` y medición manual en producción | Por implementar (CHG-017) |
| REQ-N-004 | Seguridad | Dependencias sin vulnerabilidades conocidas | 0 en backend (`pip-audit`) y frontend (`npm audit --omit=dev`) | Ejecutar ambos comandos antes de cada despliegue con cambios de dependencias | Cumple (nov. 2026) |
| REQ-N-005 | Accesibilidad | Formularios etiquetados, teclado, anuncios | 100 % de campos con `<label htmlFor>`; diálogos con foco atrapado y Esc; errores con `role="alert"` | Revisión con la guía de interfaces web + prueba manual con teclado | Cumple |
| REQ-N-006 | Costo | Costo mensual de operación | ≤ US$5/mes | Facturación de Vercel, Railway, Supabase y Brevo | Cumple |
| REQ-N-007 | Disponibilidad | La BD no se pausa por inactividad | 0 pausas al mes | Tarea programada de actividad (pendiente) | **No cumple** (backlog) |
| REQ-N-008 | Recuperación | Respaldo de datos | RPO ≤ 7 días; restauración probada | Respaldo semanal automático + simulacro (pendiente) | **No cumple** (backlog) |
| REQ-N-009 | Calidad | Puertas antes de desplegar | Pruebas del backend 100 % pasando; `npx eslint .` con 0 problemas; `npx next build` exitoso | Comandos de `CLAUDE.md` (CI pendiente) | Cumple manualmente |
| REQ-N-010 | Correo | Entrega de códigos | ≤ 250 correos/día; códigos con texto plano + HTML | `tests/test_correo.py`; actividad en Brevo | Cumple |
