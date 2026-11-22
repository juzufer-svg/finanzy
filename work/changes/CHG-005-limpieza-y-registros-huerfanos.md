# CHG-005 — Limpiar código sin uso y registros huérfanos

- **Estado:** listo-para-aprobar
- **Fecha:** 2026-11-22 · **Solicitante:** dueño del proyecto · **Riesgo:** alto (datos) · modo `completo`

## 1. Pedido original (literal)
> borrar el codigo basura o que no se use y esto: 64 registros huérfanos.

## 2. Clasificación
Deuda técnica (BL-009) + datos (BL-015) · REQ-F-013 (eliminar cuenta borra todo) · modo `completo` por tocar datos.

## 3. Análisis y decisiones
**Código sin uso (BL-009).** Se buscó con `knip` (frontend) y `vulture` (backend), más revisión manual:
- Raíz: documentos y scripts de la plantilla original, desactualizados (`API_REFERENCE.md`, `ARCHITECTURE.md`,
  `FILES.md`, `PLATAAPP.md`, `QUICKSTART.md`, `START_HERE.md`, `STRUCTURE.md`, `INFRAESTRUCTURA.txt`,
  `CHECKLIST.sh`, `SUMMARY.sh`, `check.sh`, `dev.sh`, `setup.sh`, `validate.sh`), `docker-compose.yml` (con
  claves de ejemplo y una BD local que la app no usa) y su `frontend/Dockerfile*`, un `package.json` raíz con
  React 18 que no usa nadie (Vercel compila `frontend/`), y `.devcontainer/` + `.vscode/` de una plantilla de
  Codespaces que apuntaban a archivos inexistentes. `README.md` se reescribió y apunta a la documentación vigente.
- Backend: `get_supabase()` y `SupabaseDB.close()` sin uso; variables de configuración sin uso
  (`API_V1_STR`, `PROJECT_NAME`, `SUPABASE_ANON_KEY`, `DATABASE_URL`; como `extra="ignore"`, que sigan en
  Railway no rompe nada). `ResumenTransacciones` ahora sí se usa como `response_model` del resumen.
- Frontend: `CURRENCY_SYMBOLS` y `CURRENCY_NAMES` sin uso; `CODE_LENGTH` deja de exportarse; las categorías
  "predeterminadas" falsas de `TransactionForm` (ids `default-*` que el backend rechazaba con 404) se quitan
  en CHG-007, que reescribe ese formulario.
- `PLATAAPP_SCHEMA.sql`: se quitan los `INSERT` de categorías con un usuario inexistente (origen de huérfanos),
  la vista `v_resumen_mensual` (sin uso; expone totales de todos los usuarios) y las políticas con `auth.uid()`
  (la app no usa Supabase Auth). Se documenta RLS activo sin políticas.

**Registros huérfanos (BL-015).** La revisión anterior encontró 64 filas cuyo `usuario_id` no existe en `users`
(categorías 53, transacciones 9, presupuestos 1, metas 1): faltan las llaves foráneas en la base real.
El dueño aprobó borrarlos (2026-11-22). Migraciones en `backend/sql/`, que ejecuta el dueño:
1. `2026-11-22_huerfanos_1_diagnostico.sql`: solo lectura (conteos, efecto en usuarios reales, llaves actuales).
2. `2026-11-22_huerfanos_2_respaldo_y_borrado.sql`: copia los huérfanos al esquema privado `respaldo`, los borra,
   y deja "Sin categoría" los movimientos de usuarios reales que apuntaban a una categoría huérfana (anotado en
   `respaldo.categoria_quitada`). Todo en una transacción; repetible.
3. `2026-11-22_huerfanos_3_llaves_foraneas.sql`: crea o corrige las 6 llaves foráneas (usuario → CASCADE;
   `transacciones.categoria_id` → SET NULL; `presupuestos.categoria_id` → CASCADE). Falla sin cambiar nada si
   quedara algún huérfano. Repetible.
4. `2026-11-22_quitar_vista_resumen.sql`: quita `v_resumen_mensual` si existe.

**Fuera de alcance:** la columna `presupuestos."mes_año"` (2 filas NULL). El código solo usa `mes_ano`, pero
borrar una columna es irreversible: se deja para una decisión aparte.

## 4. Spec afectada
REQ-F-013 / UC-010 / CT-002 (la cascada ya estaba especificada; ahora la garantiza la BD) · INV-021 (nuevo).

## 5. Evidencia
- SQL probado en PostgreSQL 16 local con una base que imita la real (sin llaves, columna `mes_año`, una llave
  `NO ACTION` previa y un movimiento real apuntando a una categoría huérfana): el paso 1 cuenta 53/9/1/1; el paso 3
  antes del 2 falla con mensaje claro; 2 → 3 deja 0 huérfanos y las 6 llaves; repetir 2 y 3 no cambia nada;
  borrar un usuario borra todo lo suyo y borrar una categoría deja sus movimientos sin categoría.
- `python -m pytest -q` en verde; `npx eslint .` 0 problemas; `npx next build` correcto.

## 6. Cierre
- Pendiente: el dueño ejecuta los pasos 1 → 2 → 3 (y 4) en Supabase; aprobación humana y push a `main`.

## 7. Revisión independiente
Agente `revisor` (2026-11-22): aprobado con observaciones, confianza 85 %. Corregido: el paso 2 fallaba al repetirse
después de `2026-11-22_medio_pago.sql` (respaldo con una columna menos); ahora copia por nombre de columna y agrega al
respaldo las columnas nuevas, y `probar.sh` lo repite tras esa migración. El paso 1 revisa además que las columnas de
las llaves sean `uuid`.
