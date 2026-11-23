#!/usr/bin/env bash
# Prueba las migraciones de huérfanos (CHG-005), medio de pago (CHG-007) recurrentes (CHG-012) y sin duplicados (CHG-013) en un PostgreSQL DESECHABLE.
# Crea la base de prueba finanzy_prueba_sql en el servidor indicado y trabaja solo ahí.
# Uso (CI o local): ADMIN_URL=postgresql://postgres:postgres@localhost:5432/postgres bash backend/sql/pruebas/probar.sh
set -euo pipefail
cd "$(dirname "$0")"
: "${ADMIN_URL:?Define ADMIN_URL con un PostgreSQL local o de CI (nunca el de Supabase)}"
PGOPTIONS="-c client_min_messages=warning" psql "$ADMIN_URL" -q -c "drop database if exists finanzy_prueba_sql" -c "create database finanzy_prueba_sql"
PGURL="${ADMIN_URL%/*}/finanzy_prueba_sql"
export PGOPTIONS="-c client_min_messages=warning"
run() { psql "$PGURL" -q -v ON_ERROR_STOP=1 -f "$1" > /dev/null; }
run 01_base_como_produccion.sql
psql "$PGURL" -q -v ON_ERROR_STOP=1 -f ../2026-11-22_huerfanos_1_diagnostico.sql > /dev/null
# El paso 3 antes del 2 debe fallar sin cambiar nada
if psql "$PGURL" -q -v ON_ERROR_STOP=1 -f ../2026-11-22_huerfanos_3_llaves_foraneas.sql > /dev/null 2>&1; then
  echo "ERROR: el paso 3 no debía funcionar con huérfanos"; exit 1
fi
for i in 1 2; do
  run ../2026-11-22_huerfanos_2_respaldo_y_borrado.sql
  run ../2026-11-22_huerfanos_3_llaves_foraneas.sql
done
run ../2026-11-22_quitar_vista_resumen.sql
# CHG-007: medio de pago (dos veces para comprobar que se puede repetir)
run ../2026-11-22_medio_pago.sql
run ../2026-11-22_medio_pago.sql
# Repetir el paso 2 después de medio_pago (la tabla de respaldo no tenía esa columna) debe funcionar
run ../2026-11-22_huerfanos_2_respaldo_y_borrado.sql
# CHG-012: transacciones recurrentes (dos veces para comprobar que se puede repetir)
run ../2026-11-23_recurrentes.sql
run ../2026-11-23_recurrentes.sql
PGOPTIONS="" psql "$PGURL" -q -v ON_ERROR_STOP=1 -f 02_comprobaciones.sql
# CHG-013: sin duplicados (datos repetidos, migración dos veces, comprobación)
run 03_preparar_duplicados.sql
run ../2026-11-23_sin_duplicados.sql
run ../2026-11-23_sin_duplicados.sql
PGOPTIONS="" psql "$PGURL" -q -v ON_ERROR_STOP=1 -f 04_comprobar_duplicados.sql
