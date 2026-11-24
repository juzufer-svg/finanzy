# Trazabilidad

Relación REQ → UC → Contrato → Implementación → Prueba. Se actualiza **en el mismo cambio** que el código
(skill `sdd-trazabilidad`).
Estado: `Especificado` → `Implementado` → `Verificado` (solo con pruebas automatizadas ejecutadas y aprobadas).

Rutas relativas a la raíz del repositorio. `be/` = `backend/app/`, `fe/` = `frontend/`, `t/` = `backend/tests/`.

| REQ | UC | Contrato | Implementación | Pruebas / BDD | Estado |
|---|---|---|---|---|---|
| REQ-F-001 | UC-001, WF-001 | CT-001 `register`, `verify-email`, `resend-code` | `be/api/routes/auth.py`, `be/utils/email.py`, `be/models/user.py`, `fe/app/auth/register/page.tsx` | `t/test_auth.py` (registro, verificación, 409, INV-014) · BDD-AUTH | Verificado (CA-4 limpieza de 1 h: sin prueba, depende de Supabase) |
| REQ-F-002 | UC-002 | CT-001 `login` | `be/api/routes/auth.py`, `be/core/security.py`, `fe/app/auth/login/page.tsx`, `fe/store/auth.ts`, `fe/app/api/v1/[...path]/route.ts` (cookie HttpOnly, ADR-005) | `t/test_auth.py` (login, INV-006, bloqueo, INV-011, INV-015) · BDD-AUTH | Verificado |
| REQ-F-003 | UC-003 | CT-001 `forgot-password`, `reset-password` | `be/api/routes/auth.py`, `be/models/user.py`, `be/api/sesion.py`, `fe/app/auth/forgot-password/page.tsx`, `fe/lib/code-input.ts` | `t/test_codigos.py`, `t/test_sesiones.py` (CA-4, INV-016) · BDD-RECUPERACION | Verificado |
| REQ-F-004 | UC-004 | CT-003 (v1.1 `medio_pago`) | `be/api/routes/plataapp.py`, `be/schemas/plataapp.py`, `be/models/plataapp.py`, `be/models/demo_db.py`, `backend/sql/2026-11-22_medio_pago.sql`, `fe/app/dashboard/transactions/page.tsx`, `fe/components/TransactionForm.tsx`, `fe/lib/payment-methods.ts`, `fe/app/dashboard/reports/page.tsx` (gasto por medio) | `t/test_propiedad.py`, `t/test_validaciones.py`, `t/test_medio_pago.py` (CA-4, INV-022), `frontend/tests/month-stats.test.mjs` (filtro y total por medio) · BDD-TRANSACCIONES, BDD-PROPIEDAD | Verificado |
| REQ-F-005 | UC-008 | CT-003 `GET`, `resumen/{mes}` | `be/api/routes/plataapp.py`, `fe/app/dashboard/page.tsx`, `fe/components/DashboardSummary.tsx` (vs mes anterior), `fe/components/TransactionList.tsx`, `fe/app/dashboard/transactions/page.tsx` (buscador y filtro), `fe/lib/month-stats.ts` | `t/test_validaciones.py::test_resumen_del_mes`, `::test_inv005_meses_invalidos_se_rechazan`, `frontend/tests/month-stats.test.mjs` (buscador, variación) · BDD-TRANSACCIONES | Verificado (CA-1..3 y lógica de CA-4/5; la interfaz, revisión manual) |
| REQ-F-006 | UC-005 | CT-004 | `be/api/routes/plataapp.py`, `be/models/plataapp.py` (categorías por defecto), `fe/app/dashboard/categories/page.tsx` (página propia, CA-4 CHG-012), `fe/lib/category-icons.ts` | `t/test_propiedad.py`, `t/test_validaciones.py::test_inv004_tipo_debe_ser_ingreso_o_gasto` · BDD-PROPIEDAD | Verificado (CA-4: la página, revisión manual con capturas) |
| REQ-F-007 | UC-006 | CT-005 (v1.1 `copiar`) | `be/api/routes/plataapp.py` (`copiar_presupuestos`), `be/schemas/plataapp.py`, `fe/app/dashboard/budgets/page.tsx` (copiar mes anterior), `fe/components/BudgetCard.tsx`, `fe/app/dashboard/page.tsx` + `fe/lib/month-stats.ts::budgetAlerts` (avisos CA-5) | `t/test_propiedad.py`, `t/test_validaciones.py::test_inv003_limites_objetivos_y_abonos_positivos`, `t/test_presupuestos_copia.py` (CA-4), `frontend/tests/recurrentes.test.mjs` (estado 75 %/100 % y avisos, CA-2/CA-5) · BDD-PROPIEDAD | Verificado |
| REQ-F-008 | UC-007 | CT-006 | `be/api/routes/plataapp.py`, `fe/app/dashboard/goals/page.tsx`, `fe/components/GoalProgressCard.tsx` | `t/test_metas.py::test_meta_completada_cuando_lo_ahorrado_alcanza_el_objetivo`, `t/test_propiedad.py` · BDD-METAS | Verificado |
| REQ-F-009 | UC-007, WF-002 | CT-006 `abonar` | `be/api/routes/plataapp.py::abonar_meta`, `be/models/plataapp.py::MetaDB.abonar`, `backend/sql/2026-11-22_abonar_meta_atomico.sql` | `t/test_metas.py` · BDD-METAS | Verificado |
| REQ-F-010 | UC-008 | CT-003, CT-005 `GET /presupuestos/{mes}` | `fe/app/dashboard/reports/page.tsx`, `fe/lib/month-stats.ts`, `fe/components/SpendingChart.tsx` | `frontend/tests/month-stats.test.mjs` (`npm test`, en CI; incluye fechas futuras con `upToToday`) · BDD-TRANSACCIONES | Verificado (cálculos; el gráfico, revisión manual) |
| REQ-F-011 | UC-009 | CT-002 `me/currency` | `be/api/routes/users.py`, `be/models/user.py::update_currency`, `fe/store/currency.ts` (`toInput`, `toBase`, `symbol`), `fe/lib/currency.ts`, `fe/components/MoneyPrefix.tsx`, formularios de transacciones, presupuestos, metas y recurrentes, `fe/app/dashboard/profile/page.tsx`, `fe/app/dashboard/layout.tsx` (aplica la moneda de la cuenta al entrar, CA-4), `fe/lib/currency.ts::isSupportedCurrency` | `t/test_endurecimiento.py::test_moneda_*` (guardado en servidor), `frontend/tests/currency.test.mjs` (montos en la moneda elegida, CA-3; monedas válidas, CA-4), recorrido Playwright (CHG-013, CHG-016: login en navegador nuevo y con USD viejo → COP) | Verificado (CA-3 y guardado; la conversión de la vista, sin prueba de interfaz) |
| REQ-F-012 | — | — | `fe/store/theme.ts`, `fe/components/ThemeProvider.tsx` | — | Implementado |
| REQ-F-013 | UC-010 | CT-002 `DELETE me` | `be/api/routes/users.py`, `be/models/user.py`, `fe/app/dashboard/profile/page.tsx`, llaves foráneas `backend/sql/2026-11-22_huerfanos_3_llaves_foraneas.sql` (CHG-005) | `backend/sql/pruebas/probar.sh` (cascada en la BD, INV-021) | Implementado (la cascada se verifica en CI; el endpoint, sin prueba) |
| REQ-F-014 | — | CT-002 `GET me`, `PUT me`, `POST me/password` (v1.1) | `be/api/routes/users.py` (`update_profile`, `change_password`), `be/models/user.py::update_full_name`, `be/schemas/auth.py`, `fe/app/api/v1/[...path]/route.ts` (`TOKEN_ROUTES`), `fe/components/ProfileForms.tsx`, `fe/app/dashboard/profile/page.tsx` | `t/test_perfil.py` (CA-2, CA-3, INV-027, INV-018) | Verificado (CA-2/CA-3 backend; CA-1 y la interfaz, revisión manual) |
| REQ-F-015 | UC-011 | CT-007 | `be/api/routes/asistente.py`, `be/utils/asistente.py`, `be/schemas/asistente.py`, `be/core/config.py` (`ANTHROPIC_*`, `ASISTENTE_*`), `fe/app/dashboard/assistant/page.tsx`, `fe/app/dashboard/layout.tsx` (menú y botón de la barra superior) | `t/test_asistente.py` (INV-023, INV-024; la API de Claude se simula) | Verificado (backend; la pantalla del chat, revisión manual) |
| REQ-F-016 | UC-012 | CT-008 | `be/api/routes/plataapp.py` (recurrentes), `be/utils/recurrencia.py`, `be/schemas/plataapp.py`, `be/models/plataapp.py::RecurrenteDB`, `be/models/demo_db.py::DemoRecurrenteDB`, `backend/sql/2026-11-23_recurrentes.sql`, `fe/app/dashboard/recurring/page.tsx`, `fe/components/PendingRecurring.tsx`, `fe/app/dashboard/page.tsx`, `fe/lib/recurrentes.ts` | `t/test_recurrentes.py` (INV-025, INV-026, INV-001, INV-002), `backend/sql/pruebas/02_comprobaciones.sql` (CHECK, FK, RLS), `frontend/tests/recurrentes.test.mjs` · BDD-RECURRENTES | Verificado (falta ejecutar el SQL en Supabase antes del despliegue) |
| REQ-F-017 | UC-013 | CT-009 | `be/api/routes/whatsapp.py`, `be/utils/whatsapp.py`, `be/models/whatsapp.py`, `be/core/config.py` (`WHATSAPP_*`), `backend/sql/2026-11-23_whatsapp.sql`, `fe/components/WhatsAppCard.tsx`, `fe/app/dashboard/profile/page.tsx`, `docs/WHATSAPP.md`, ADR-007 | `t/test_whatsapp.py` (INV-029, INV-030; Claude y Meta simulados), `backend/sql/pruebas/05_comprobar_whatsapp.sql`, recorrido Playwright del enlace con webhook firmado · BDD-WHATSAPP | Verificado (con Meta y Claude simulados; la prueba real la hace el dueño tras configurar Meta) |
| REQ-N-001 | — | Todos | `be/api/routes/plataapp.py::_ensure_owner`, `::_ensure_categoria_propia`, `be/models/plataapp.py` (filtro `usuario_id`) | `t/test_propiedad.py`, `t/test_endurecimiento.py` (INV-001, INV-002) | Verificado |
| REQ-N-002 | — | CT-001 | `be/core/rate_limit.py`, `be/api/routes/auth.py` | `t/test_limites.py`, `t/test_auth.py::test_inv010_login_se_bloquea_tras_5_fallos` (INV-010) | Verificado |
| REQ-N-003 | — | — | `be/main.py`, `be/core/config.py`, `be/utils/email.py`, `fe/next.config.js` (cabeceras) | `t/test_app_seguridad.py`, `t/test_correo.py`, `t/test_endurecimiento.py` (INV-012, INV-013, INV-019) | Verificado (cabeceras: comprobación manual con `curl -I`) |
| REQ-N-004 | — | — | `backend/requirements.txt`, `frontend/package.json` | `pip-audit` en CI (`.github/workflows/ci.yml`); `npm audit` manual | Implementado |
| REQ-N-005 | — | — | `fe/components/DialogProvider.tsx`, `fe/components/ErrorState.tsx`, formularios, `fe/app/dashboard/layout.tsx` (nombres accesibles, `aria-current`, Esc en el menú móvil; el menú móvil se cierra en cada cambio de ruta, CHG-011), `fe/components/PageHeader.tsx`, `fe/components/PeriodPicker.tsx` + `fe/store/period.ts` (período compartido, CHG-009), `fe/app/globals.css` (`reveal-on-hover`, campos de 16 px en móvil) (CHG-008) | Revisión manual + capturas PC/iPhone (CHG-008); recorrido Playwright del menú móvil y el Asistente IA (CHG-011); `frontend/tests/month-stats.test.mjs` (`monthTitle`, `shortDate`, `isValidMonth`) | Implementado |
| REQ-N-007 | — | — | — | — | Especificado (backlog) |
| REQ-N-008 | — | — | — | — | Especificado (backlog) |
| REQ-N-009 | — | — | `.github/workflows/ci.yml` (pytest, pip-audit, eslint, next build en cada push y PR) | El propio CI | Implementado |
| REQ-N-010 | — | — | `be/utils/email.py` (Brevo) | `t/test_correo.py` | Verificado |

## Invariantes → pruebas

| INV | Pruebas |
|---|---|
| INV-001 | `test_propiedad.py::test_inv001_*`, `test_endurecimiento.py::test_toda_consulta_por_id_en_supabase_filtra_tambien_por_usuario`, `::test_modo_demo_no_borra_ni_edita_registros_de_otro_usuario` |
| INV-002 | `test_propiedad.py::test_inv002_no_se_puede_usar_una_categoria_ajena` |
| INV-003 | `test_validaciones.py::test_inv003_*` |
| INV-004 | `test_validaciones.py::test_inv004_tipo_debe_ser_ingreso_o_gasto` |
| INV-005 | `test_validaciones.py::test_inv005_*` |
| INV-006 | `test_auth.py::test_inv006_cuenta_pendiente_no_obtiene_sesion` |
| INV-007 | `test_codigos.py::test_inv007_*` |
| INV-008 | `test_metas.py::test_inv008_*`, `test_metas_atomico.py::*` (concurrencia real probada en PostgreSQL, CHG-004) |
| INV-009 | `test_codigos.py::test_inv009_*`, `test_limites.py::test_forgot_password_aplica_el_limite_diario_en_silencio` |
| INV-010 | `test_limites.py::*`, `test_auth.py::test_inv010_login_se_bloquea_tras_5_fallos` |
| INV-011 | `test_auth.py::test_inv011_*` |
| INV-012 | `test_app_seguridad.py::test_inv012_*`, `test_correo.py::test_inv012_*` |
| INV-013 | `test_app_seguridad.py::test_inv013_*` |
| INV-014 | `test_auth.py::test_inv014_correo_se_normaliza_a_minusculas` |
| INV-015 | `test_auth.py::test_inv015_*` |
| INV-016 | `test_whatsapp.py::test_h2_*` (WhatsApp se desconecta), `test_sesiones.py::test_inv016_*`, `test_sesiones.py::test_login_y_verificacion_emiten_la_version_de_sesion_vigente` |
| INV-017 | `test_endurecimiento.py::test_inv017_*` |
| INV-018 | `test_endurecimiento.py::test_inv018_*` |
| INV-019 | `test_endurecimiento.py` (configuración y CORS) |
| INV-020 | `frontend/e2e/sesion-cookie.mjs` (prueba de punta a punta con Playwright; manual, sin CI todavía) |
| INV-021 | `backend/sql/pruebas/probar.sh` + `02_comprobaciones.sql` (CI, job "Migraciones SQL") |
| INV-022 | `test_medio_pago.py::test_inv022_*`, `backend/sql/pruebas/02_comprobaciones.sql` (CHECK en la BD) |
| INV-023 | `test_asistente.py::test_inv023_*` |
| INV-025 | `test_recurrentes.py::test_inv025_*` |
| INV-026 | `test_recurrentes.py::test_inv026_*`, `backend/sql/pruebas/02_comprobaciones.sql` |
| INV-027 | `test_perfil.py::test_inv027_*` |
| INV-028 | `test_sin_duplicados.py::*`, `backend/sql/pruebas/04_comprobar_duplicados.sql` |
| INV-029 | `test_whatsapp.py::test_inv029_*`, `backend/sql/pruebas/05_comprobar_whatsapp.sql` |
| INV-030 | `test_whatsapp.py::test_inv030_*` |
| INV-024 | `test_asistente.py::test_inv024_*`, `::test_sin_clave_responde_503_y_no_llama_a_claude`, `::test_ultima_ronda_obliga_a_responder_sin_herramientas` |

## Huérfanos (deben quedar vacíos)
- REQ sin prueba automatizada: REQ-F-011 (conversión de la vista; los formularios sí, CHG-013), REQ-F-012, REQ-F-013 (endpoint; la cascada sí se prueba en el CI de SQL), REQ-F-014 CA-1 (ver BL-010; CA-2/CA-3 ya tienen `t/test_perfil.py`, CHG-012). REQ-F-010 ya tiene `npm test` (CHG-006).
- Código sin REQ: ninguno conocido.
