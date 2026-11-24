#!/usr/bin/env bash
# Prueba las migraciones de huérfanos (CHG-005), medio de pago (CHG-007) recurrentes (CHG-012) sin duplicados (CHG-013) WhatsApp (CHG-014) y monitor de consumos (CHG-017) y estado de autenticación persistente (CHG-020) en un PostgreSQL DESECHABLE.
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
# CHG-014: WhatsApp (dos veces para comprobar que se puede repetir)
run ../2026-11-23_whatsapp.sql
run ../2026-11-23_whatsapp.sql
PGOPTIONS="" psql "$PGURL" -q -v ON_ERROR_STOP=1 -f 05_comprobar_whatsapp.sql
# CHG-017: monitor de consumos (dos veces para comprobar que se puede repetir)
run ../2026-11-24_monitor.sql
run ../2026-11-24_monitor.sql
run ../2026-11-24_monitor_tamano_bd.sql
run ../2026-11-24_monitor_tamano_bd.sql
PGOPTIONS="" psql "$PGURL" -q -v ON_ERROR_STOP=1 -f 06_comprobar_monitor.sql
# Incremento atómico con dos sesiones simultáneas: contador de hoy en 10 + incrementos de 1 y de 2 = 13
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "select public.incrementar_contador(current_date, 'whatsapp_enviados', 'general', 10)" > /dev/null
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; select public.incrementar_contador(current_date, 'whatsapp_enviados', 'general', 1); select pg_sleep(1.5); commit;" > /dev/null &
sleep 0.5   # la segunda sesión entra mientras la primera aún no confirmó: debe esperar y sumar, no pisar
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "select public.incrementar_contador(current_date, 'whatsapp_enviados', 'general', 2)" > /dev/null
wait
TOTAL=$(psql "$PGURL" -q -t -A -c "select cantidad from public.contadores_diarios where fecha = current_date and metrica = 'whatsapp_enviados' and origen = 'general'")
if [ "$TOTAL" != "13" ]; then echo "ERROR: incremento simultáneo dio $TOTAL (esperado 13)"; exit 1; fi
echo "OK: incremento atómico simultáneo = 13"
# CHG-020: estado de autenticación persistente (dos veces para comprobar que se puede repetir).
# El rol service_role existe en Supabase (con BYPASSRLS); aquí se crea igual para probar los GRANT y las funciones con su rol.
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "do \$\$ begin if not exists (select 1 from pg_roles where rolname='service_role') then create role service_role bypassrls; end if; end \$\$"
# Como en Supabase: los tres roles pueden usar el esquema public (lo que les falta lo deciden los GRANT/REVOKE de cada objeto)
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "grant usage on schema public to anon, authenticated, service_role"
run ../2026-11-24_auth_persistente.sql
run ../2026-11-24_auth_persistente.sql
PGOPTIONS="" psql "$PGURL" -q -v ON_ERROR_STOP=1 -f 07_comprobar_auth_persistente.sql
# Concurrencia real: una sesión retiene el bloqueo y N sesiones simultáneas hacen cola sobre él (así todas compiten de verdad)
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
sql() { psql "$PGURL" -q -t -A -v ON_ERROR_STOP=1 -c "$1"; }
# $1 = sentencia que retiene el bloqueo 2 s; $2 = cantidad; $3 = sentencia de cada sesión (resultado en $TMP/r.N)
en_paralelo() {
  psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; $1; select pg_sleep(2); commit;" > /dev/null &
  sleep 0.7   # el bloqueador ya tiene el bloqueo
  for n in $(seq 1 "$2"); do sql "$3" > "$TMP/r.$n" & done
  wait
}
cuenta() { cat "$TMP"/r.* | grep -c -x "$1" || true; }
esperar() { if [ "$2" != "$3" ]; then echo "ERROR: $1 dio $2 (esperado $3)"; exit 1; fi; echo "OK: $1 = $2"; }

# 6 reservas de login simultáneas -> exactamente 5 permitidas (la 6.ª recibe 429)
sql "insert into public.auth_login_intentos(clave) values ('conc_login')" > /dev/null
rm -f "$TMP"/r.*
en_paralelo "select 1 from public.auth_login_intentos where clave = 'conc_login' for update" 6 "select permitido from public.auth_login_reservar('conc_login')"
esperar "6 reservas simultáneas permitidas" "$(cuenta t)" 5
esperar "6 reservas simultáneas rechazadas" "$(cuenta f)" 1
esperar "fallos tras 6 reservas simultáneas" "$(sql "select fallos from public.auth_login_intentos where clave = 'conc_login'")" 5
# La 5.ª reserva que acierta (con 4 más en vuelo): entra, se le devuelve el intento y el correo queda desbloqueado
sql "select public.auth_login_resolver('conc_login', true)" > /dev/null
esperar "5.ª reserva que acierta: fallos y bloqueo" "$(sql "select fallos || '/' || (bloqueado_hasta is null) || '/' || en_vuelo from public.auth_login_intentos where clave = 'conc_login'")" "4/true/4"
sql "delete from public.auth_login_intentos" > /dev/null

# Un código de un solo uso con 2 sesiones simultáneas: una sola acierta
sql "select public.auth_codigo_emitir('conc_cod', 'verify', 'hmac_ok')" > /dev/null
rm -f "$TMP"/r.*
en_paralelo "select 1 from public.auth_codigos where clave = 'conc_cod' for update" 2 "select public.auth_codigo_verificar('conc_cod', 'verify', 'hmac_ok')"
esperar "verificaciones simultáneas con ok" "$(cuenta ok)" 1
esperar "verificaciones simultáneas con invalido" "$(cuenta invalido)" 1
# 40 verificaciones incorrectas simultáneas: como mucho 5 se evalúan; después ni el código correcto lo activa
sql "select public.auth_codigo_emitir('conc_cod2', 'verify', 'hmac_ok')" > /dev/null
rm -f "$TMP"/r.*
en_paralelo "select 1 from public.auth_codigos where clave = 'conc_cod2' for update" 40 "select public.auth_codigo_verificar('conc_cod2', 'verify', 'hmac_mal')"
esperar "40 verificaciones incorrectas: incorrecto" "$(cuenta incorrecto)" 5
esperar "40 verificaciones incorrectas: invalido" "$(cuenta invalido)" 35
esperar "código correcto tras agotar los intentos" "$(sql "select public.auth_codigo_verificar('conc_cod2', 'verify', 'hmac_ok')")" invalido
sql "delete from public.auth_codigos; delete from public.auth_limites_eventos where clave <> 'purga'" > /dev/null

# 10 emisiones simultáneas al mismo correo -> 1 enviado y 9 reciente (60 s)
rm -f "$TMP"/r.*
en_paralelo "select pg_advisory_xact_lock(hashtextextended('auth_emitir:correo:conc_mail', 0))" 10 "select public.auth_codigo_emitir('conc_mail', 'verify', 'h')"
esperar "10 emisiones simultáneas: enviado" "$(cuenta enviado)" 1
esperar "10 emisiones simultáneas: reciente" "$(cuenta reciente)" 9
sql "delete from public.auth_codigos; delete from public.auth_limites_eventos where clave <> 'purga'" > /dev/null

# 15 emisiones simultáneas (p_espacio_seg = 0) a un destinatario con 5 eventos previos -> 5 enviado y 10 limitado (tope de 10/día)
sql "insert into public.auth_limites_eventos(clave, tipo, ocurrido_en) select 'conc_tope', 'correo', now() - interval '1 hour' from generate_series(1, 5)" > /dev/null
rm -f "$TMP"/r.*
en_paralelo "select pg_advisory_xact_lock(hashtextextended('auth_emitir:correo:conc_tope', 0))" 15 "select public.auth_codigo_emitir('conc_tope', 'verify', 'h', 0)"
esperar "15 emisiones simultáneas: enviado" "$(cuenta enviado)" 5
esperar "15 emisiones simultáneas: limitado" "$(cuenta limitado)" 10
esperar "eventos del destinatario tras las 15 emisiones" "$(sql "select count(*) from public.auth_limites_eventos where clave = 'conc_tope' and tipo = 'correo'")" 10
# Límite por IP simultáneo: 40 intentos con límite 30 -> 30 ok y 10 limitado
rm -f "$TMP"/r.*
en_paralelo "select pg_advisory_xact_lock(hashtextextended('auth_limite:conc_ip:ip_intento', 0))" 40 "select public.auth_limite_registrar('conc_ip', 'ip_intento', 30, 600)"
esperar "40 intentos por IP simultáneos: ok" "$(cuenta ok)" 30
esperar "40 intentos por IP simultáneos: limitado" "$(cuenta limitado)" 10
# I-4: la purga es una llamada aparte; ni espera a la emisión de códigos ni la hace esperar ni causa errores o interbloqueos
# (a) otra sesión retiene el bloqueo de purga: auth_purgar devuelve -1 de inmediato y la emisión no espera
sql "delete from public.auth_login_intentos; delete from public.auth_codigos; delete from public.auth_limites_eventos" > /dev/null
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; select pg_advisory_xact_lock(hashtextextended('auth_purgar', 0)); select pg_sleep(2); commit;" > /dev/null &
sleep 0.7
T0=$(date +%s%N)
esperar "auth_purgar con otra sesión purgando" "$(sql "select public.auth_purgar()")" -1
esperar "emisión mientras otra sesión purga" "$(sql "select public.auth_codigo_emitir('conc_pa', 'verify', 'h')")" enviado
MS=$(( ($(date +%s%N) - T0) / 1000000 ))
if [ "$MS" -gt 1200 ]; then echo "ERROR: la purga bloqueó la emisión ($MS ms)"; exit 1; fi
echo "OK: ni la purga ni la emisión esperaron al bloqueo de purga ($MS ms)"
wait
# (b) una purga grande (600 000 eventos vencidos) a la vez que 10 emisiones al mismo correo y 5 a otros: sin errores ni interbloqueos
sql "delete from public.auth_limites_eventos" > /dev/null
sql "insert into public.auth_limites_eventos(clave, tipo, ocurrido_en) select 'vencido' || g, 'correo', now() - interval '3 days' from generate_series(1, 600000) g" > /dev/null
rm -f "$TMP"/r.*
sql "select public.auth_purgar(now(), 1000000)" > "$TMP/purga" &
sleep 0.2
for n in $(seq 1 10); do sql "select public.auth_codigo_emitir('conc_pb', 'verify', 'h')" > "$TMP/r.$n" & done
for n in $(seq 11 15); do sql "select public.auth_codigo_emitir('conc_pb$n', 'reset', 'h')" > "$TMP/r.$n" & done
wait
esperar "purga grande a la vez que emisiones: enviado" "$(cuenta enviado)" 6
esperar "purga grande a la vez que emisiones: reciente" "$(cuenta reciente)" 9
esperar "purga grande: filas vencidas borradas" "$(cat "$TMP/purga")" 600000
esperar "purga grande: no tocó los eventos de las emisiones" "$(sql "select count(*) from public.auth_limites_eventos where clave like 'conc_pb%' and tipo = 'correo'")" 6
sql "delete from public.auth_login_intentos; delete from public.auth_codigos; delete from public.auth_limites_eventos" > /dev/null
echo "OK: concurrencia real del estado de autenticación"
