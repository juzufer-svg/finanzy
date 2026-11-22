# Requisitos no funcionales (medibles)

| ID | Categoría | Requisito | Valor objetivo | Cómo se mide / prueba | Estado |
|---|---|---|---|---|---|
| REQ-N-001 | Seguridad | Aislamiento de datos entre usuarios | 100 % de operaciones por ID verifican dueño | `tests/test_propiedad.py` (INV-001, INV-002) | Cumple |
| REQ-N-002 | Seguridad | Fuerza bruta y abuso de correo limitados | Límites de INV-010 | `tests/test_limites.py`, `tests/test_auth.py` | Cumple |
| REQ-N-003 | Seguridad | Sin secretos en código, logs ni frontend; sin diagnóstico; cabeceras de seguridad (CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, HSTS) | 0 secretos; cabeceras presentes en todas las rutas | `tests/test_app_seguridad.py`, `tests/test_correo.py`; `curl -I https://finanzyapp.vercel.app` | Cumple |
| REQ-N-004 | Seguridad | Dependencias sin vulnerabilidades conocidas | 0 en backend (`pip-audit`) y frontend (`npm audit --omit=dev`) | Ejecutar ambos comandos antes de cada despliegue con cambios de dependencias | Cumple (nov. 2026) |
| REQ-N-005 | Accesibilidad | Formularios etiquetados, teclado, anuncios | 100 % de campos con `<label htmlFor>`; diálogos con foco atrapado y Esc; errores con `role="alert"` | Revisión con la guía de interfaces web + prueba manual con teclado | Cumple |
| REQ-N-006 | Costo | Costo mensual de operación | ≤ US$5/mes | Facturación de Vercel, Railway, Supabase y Brevo | Cumple |
| REQ-N-007 | Disponibilidad | La BD no se pausa por inactividad | 0 pausas al mes | Tarea programada de actividad (pendiente) | **No cumple** (backlog) |
| REQ-N-008 | Recuperación | Respaldo de datos | RPO ≤ 7 días; restauración probada | Respaldo semanal automático + simulacro (pendiente) | **No cumple** (backlog) |
| REQ-N-009 | Calidad | Puertas antes de desplegar | Pruebas del backend 100 % pasando; `npx eslint .` con 0 problemas; `npx next build` exitoso | Comandos de `CLAUDE.md` (CI pendiente) | Cumple manualmente |
| REQ-N-010 | Correo | Entrega de códigos | ≤ 250 correos/día; códigos con texto plano + HTML | `tests/test_correo.py`; actividad en Brevo | Cumple |
