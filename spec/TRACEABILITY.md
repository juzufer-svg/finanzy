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
| REQ-F-004 | UC-004 | CT-003 | `be/api/routes/plataapp.py`, `be/schemas/plataapp.py`, `be/models/plataapp.py`, `fe/app/dashboard/transactions/page.tsx`, `fe/components/TransactionForm.tsx` | `t/test_propiedad.py`, `t/test_validaciones.py` · BDD-TRANSACCIONES, BDD-PROPIEDAD | Verificado |
| REQ-F-005 | UC-008 | CT-003 `GET`, `resumen/{mes}` | `be/api/routes/plataapp.py`, `fe/app/dashboard/page.tsx`, `fe/components/DashboardSummary.tsx`, `fe/components/TransactionList.tsx` | `t/test_validaciones.py::test_resumen_del_mes`, `::test_inv005_meses_invalidos_se_rechazan` · BDD-TRANSACCIONES | Verificado |
| REQ-F-006 | UC-005 | CT-004 | `be/api/routes/plataapp.py`, `be/models/plataapp.py` (categorías por defecto), `fe/app/dashboard/transactions/page.tsx` (CategoriesManagerModal) | `t/test_propiedad.py`, `t/test_validaciones.py::test_inv004_tipo_debe_ser_ingreso_o_gasto` · BDD-PROPIEDAD | Verificado |
| REQ-F-007 | UC-006 | CT-005 | `be/api/routes/plataapp.py`, `fe/app/dashboard/budgets/page.tsx`, `fe/components/BudgetCard.tsx` | `t/test_propiedad.py`, `t/test_validaciones.py::test_inv003_limites_objetivos_y_abonos_positivos` · BDD-PROPIEDAD | Verificado (avance calculado en frontend: sin prueba automatizada) |
| REQ-F-008 | UC-007 | CT-006 | `be/api/routes/plataapp.py`, `fe/app/dashboard/goals/page.tsx`, `fe/components/GoalProgressCard.tsx` | `t/test_metas.py::test_meta_completada_cuando_lo_ahorrado_alcanza_el_objetivo`, `t/test_propiedad.py` · BDD-METAS | Verificado |
| REQ-F-009 | UC-007, WF-002 | CT-006 `abonar` | `be/api/routes/plataapp.py::abonar_meta` | `t/test_metas.py` · BDD-METAS | Verificado |
| REQ-F-010 | UC-008 | CT-003 | `fe/app/dashboard/reports/page.tsx` | — (cálculos en frontend) | Implementado |
| REQ-F-011 | UC-009 | CT-002 `me/currency` | `be/api/routes/users.py`, `be/models/user.py::update_currency`, `fe/store/currency.ts`, `fe/lib/currency.ts`, `fe/app/dashboard/profile/page.tsx` | `t/test_endurecimiento.py::test_moneda_*` (guardado en servidor; conversión en frontend sin prueba) | Implementado |
| REQ-F-012 | — | — | `fe/store/theme.ts`, `fe/components/ThemeProvider.tsx` | — | Implementado |
| REQ-F-013 | UC-010 | CT-002 `DELETE me` | `be/api/routes/users.py`, `be/models/user.py`, `fe/app/dashboard/profile/page.tsx` | — | Implementado |
| REQ-F-014 | — | CT-002 `GET me` | `be/api/routes/users.py`, `fe/app/dashboard/profile/page.tsx` | — | Implementado |
| REQ-N-001 | — | Todos | `be/api/routes/plataapp.py::_ensure_owner`, `::_ensure_categoria_propia`, `be/models/plataapp.py` (filtro `usuario_id`) | `t/test_propiedad.py`, `t/test_endurecimiento.py` (INV-001, INV-002) | Verificado |
| REQ-N-002 | — | CT-001 | `be/core/rate_limit.py`, `be/api/routes/auth.py` | `t/test_limites.py`, `t/test_auth.py::test_inv010_login_se_bloquea_tras_5_fallos` (INV-010) | Verificado |
| REQ-N-003 | — | — | `be/main.py`, `be/core/config.py`, `be/utils/email.py`, `fe/next.config.js` (cabeceras) | `t/test_app_seguridad.py`, `t/test_correo.py`, `t/test_endurecimiento.py` (INV-012, INV-013, INV-019) | Verificado (cabeceras: comprobación manual con `curl -I`) |
| REQ-N-004 | — | — | `backend/requirements.txt`, `frontend/package.json` | `pip-audit` en CI (`.github/workflows/ci.yml`); `npm audit` manual | Implementado |
| REQ-N-005 | — | — | `fe/components/DialogProvider.tsx`, `fe/components/ErrorState.tsx`, formularios | Revisión manual | Implementado |
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
| INV-008 | `test_metas.py::test_inv008_*` |
| INV-009 | `test_codigos.py::test_inv009_*`, `test_limites.py::test_forgot_password_aplica_el_limite_diario_en_silencio` |
| INV-010 | `test_limites.py::*`, `test_auth.py::test_inv010_login_se_bloquea_tras_5_fallos` |
| INV-011 | `test_auth.py::test_inv011_*` |
| INV-012 | `test_app_seguridad.py::test_inv012_*`, `test_correo.py::test_inv012_*` |
| INV-013 | `test_app_seguridad.py::test_inv013_*` |
| INV-014 | `test_auth.py::test_inv014_correo_se_normaliza_a_minusculas` |
| INV-015 | `test_auth.py::test_inv015_*` |
| INV-016 | `test_sesiones.py::test_inv016_*`, `test_sesiones.py::test_login_y_verificacion_emiten_la_version_de_sesion_vigente` |
| INV-017 | `test_endurecimiento.py::test_inv017_*` |
| INV-018 | `test_endurecimiento.py::test_inv018_*` |
| INV-019 | `test_endurecimiento.py` (configuración y CORS) |
| INV-020 | `frontend/e2e/sesion-cookie.mjs` (prueba de punta a punta con Playwright; manual, sin CI todavía) |

## Huérfanos (deben quedar vacíos)
- REQ sin prueba automatizada: REQ-F-010, REQ-F-011, REQ-F-012, REQ-F-013, REQ-F-014 (lógica en frontend o de bajo riesgo; sin pruebas de frontend todavía — ver backlog).
- Código sin REQ: ninguno conocido.
