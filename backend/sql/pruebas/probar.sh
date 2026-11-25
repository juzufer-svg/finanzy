#!/usr/bin/env bash
# Prueba las migraciones de huérfanos (CHG-005), medio de pago (CHG-007) recurrentes (CHG-012) sin duplicados (CHG-013) WhatsApp (CHG-014) y monitor de consumos (CHG-017) estado de autenticación persistente (CHG-020) y panel de administración de usuarios (CHG-023), cuentas de dinero (CHG-019 a) transferencias entre cuentas (CHG-024) y su integración con metas y recurrentes (CHG-025) en un PostgreSQL DESECHABLE.
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
# (a2) I-A: auth_limite_registrar libera vencidas con bloqueo «try»: con otra sesión purgando NO espera y no libera nada;
# sin esa sesión libera un lote pequeño (200) en cada llamada
sql "delete from public.auth_limites_eventos" > /dev/null
sql "insert into public.auth_limites_eventos(clave, tipo, ocurrido_en) select 'vencido' || g, 'ip_intento', now() - interval '3 days' from generate_series(1, 1000) g" > /dev/null
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; select pg_advisory_xact_lock(hashtextextended('auth_purgar', 0)); select pg_sleep(2); commit;" > /dev/null &
sleep 0.7
T0=$(date +%s%N)
esperar "límite por IP mientras otra sesión purga" "$(sql "select public.auth_limite_registrar('conc_lim', 'ip_intento', 30, 600)")" ok
MS=$(( ($(date +%s%N) - T0) / 1000000 ))
if [ "$MS" -gt 1200 ]; then echo "ERROR: el límite por IP esperó a la purga ($MS ms)"; exit 1; fi
esperar "vencidas con otra sesión purgando (no se liberan)" "$(sql "select count(*) from public.auth_limites_eventos where clave like 'vencido%'")" 1000
wait
esperar "límite por IP sin otra purga" "$(sql "select public.auth_limite_registrar('conc_lim2', 'ip_intento', 30, 600)")" ok
esperar "vencidas tras una llamada sin bloqueo (lote pequeño de 200)" "$(sql "select count(*) from public.auth_limites_eventos where clave like 'vencido%'")" 800
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

# CHG-023: panel de administración de usuarios (dos veces para comprobar que se puede repetir).
# La base de prueba tiene un `users` mínimo: se le añaden las columnas de producción y los permisos que Supabase da a service_role.
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "alter table public.users add column if not exists hashed_password text, add column if not exists full_name text, add column if not exists is_active boolean default true, add column if not exists currency text default 'USD', add column if not exists session_version integer not null default 0, add column if not exists created_at timestamp, add column if not exists updated_at timestamp; alter table public.users alter column created_at set default now(); grant all on all tables in schema public to service_role"
run ../2026-11-25_admin_usuarios.sql
run ../2026-11-25_admin_usuarios.sql
PGOPTIONS="" psql "$PGURL" -q -v ON_ERROR_STOP=1 -f 11_comprobar_admin_usuarios.sql
U1='00000000-0000-4000-8000-0000000000a1'; U2='00000000-0000-4000-8000-0000000000a2'; U3='00000000-0000-4000-8000-0000000000a3'
sql "insert into public.users(id, email, hashed_password, full_name, is_active, currency, session_version) values ('$U1','adm_c1@x.test','h','C1',true,'COP',0),('$U2','adm_c2@x.test','h','C2',true,'COP',0),('$U3','adm_c3@x.test','h','C3',true,'COP',0)" > /dev/null
# INV-056: dos suspensiones simultáneas del mismo usuario -> una ok, una ya; una sola fila de auditoría; versión + 1
rm -f "$TMP"/r.*
en_paralelo "select 1 from public.users where id = '$U1' for update" 2 "select public.admin_suspender_usuario('$U1')"
esperar "2 suspensiones simultáneas: ok" "$(cuenta ok)" 1
esperar "2 suspensiones simultáneas: ya" "$(cuenta ya)" 1
esperar "2 suspensiones simultáneas: filas de auditoría" "$(sql "select count(*) from public.auditoria_admin where usuario_id = '$U1' and accion = 'suspender'")" 1
esperar "2 suspensiones simultáneas: versión de sesión" "$(sql "select session_version from public.users where id = '$U1'")" 1
# INV-057: dos cierres de sesión simultáneos suben la versión en 2 (con 2 registros)
rm -f "$TMP"/r.*
en_paralelo "select 1 from public.users where id = '$U2' for update" 2 "select public.admin_cerrar_sesiones_usuario('$U2')"
esperar "2 cierres simultáneos: ok" "$(cuenta ok)" 2
esperar "2 cierres simultáneos: versión de sesión" "$(sql "select session_version from public.users where id = '$U2'")" 2
esperar "2 cierres simultáneos: filas de auditoría" "$(sql "select count(*) from public.auditoria_admin where usuario_id = '$U2' and accion = 'cerrar_sesiones'")" 2
# INV-061: 20 registrar_acceso simultáneos -> exactamente una escritura
rm -f "$TMP"/r.*
en_paralelo "select 1 from public.users where id = '$U3' for update" 20 "select public.registrar_acceso('$U3')"
esperar "20 registrar_acceso simultáneos: true" "$(cuenta t)" 1
esperar "20 registrar_acceso simultáneos: false" "$(cuenta f)" 19
# Suspender + inicio de sesión (registrar_acceso) a la vez: sin errores ni interbloqueo; estado final coherente (suspendida y versión + 1 juntas)
sql "update public.users set ultimo_acceso = null where id = '$U3'" > /dev/null
rm -f "$TMP"/r.*
en_paralelo "select 1 from public.users where id = '$U3' for update" 1 "select public.admin_suspender_usuario('$U3')"
sql "select public.registrar_acceso('$U3')" > "$TMP/acceso" &
wait
esperar "suspender + inicio de sesión: estado final" "$(sql "select suspendida || '/' || session_version || '/' || (ultimo_acceso is not null) from public.users where id = '$U3'")" "true/1/true"
# Eliminar + suspender simultáneos: cada ok deja exactamente su registro y no queda nada a medias
U4='00000000-0000-4000-8000-0000000000a4'
sql "insert into public.users(id, email, hashed_password, full_name, is_active, currency) values ('$U4','adm_c4@x.test','h','C4',true,'COP')" > /dev/null
rm -f "$TMP"/r.*
en_paralelo "select 1 from public.users where id = '$U4' for update" 1 "select public.admin_eliminar_usuario('$U4', 'adm_c4@x.test')"
sql "select public.admin_suspender_usuario('$U4')" > "$TMP/r.2" &
wait
esperar "eliminar + suspender: la cuenta ya no existe" "$(sql "select count(*) from public.users where id = '$U4'")" 0
esperar "eliminar + suspender: eliminar ok" "$(cuenta ok)" "$(sql "select count(*) from public.auditoria_admin where usuario_id = '$U4'")"
# Tope de auditoría con otra sesión limpiando: el try-lock no espera y no recorta; sin esa sesión recorta
sql "delete from public.auditoria_admin; insert into public.auditoria_admin(creado_en, accion, usuario_id) select now() - (g || ' seconds')::interval, 'suspender', gen_random_uuid() from generate_series(1, 10005) g" > /dev/null
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; select pg_advisory_xact_lock(hashtextextended('admin_auditoria_limpieza', 0)); select pg_sleep(2); commit;" > /dev/null &
sleep 0.7
T0=$(date +%s%N)
sql "select public.admin_registrar_auditoria('reactivar', gen_random_uuid())" > /dev/null
MS=$(( ($(date +%s%N) - T0) / 1000000 ))
if [ "$MS" -gt 1200 ]; then echo "ERROR: el tope de auditoría esperó a otra limpieza ($MS ms)"; exit 1; fi
esperar "tope con otra sesión limpiando (no recorta)" "$(sql "select count(*) from public.auditoria_admin")" 10006
wait
sql "select public.admin_registrar_auditoria('reactivar', gen_random_uuid())" > /dev/null
esperar "tope sin otra sesión (recorta a 10000)" "$(sql "select count(*) from public.auditoria_admin")" 10000
sql "delete from public.auditoria_admin; delete from public.users where email like 'adm\_c%@x.test'" > /dev/null
echo "OK: concurrencia real del panel de administración"

# CHG-019 fase (a): cuentas de dinero con saldo derivado (dos veces para comprobar que se puede repetir).
# Después del panel de administración: la base de prueba ya tiene las columnas de producción de `users` y los permisos de service_role.
run ../2026-11-25_cuentas.sql
run ../2026-11-25_cuentas.sql
PGOPTIONS="" psql "$PGURL" -q -v ON_ERROR_STOP=1 -f 08_comprobar_cuentas.sql
# Concurrencia real con los disparadores BEFORE fz001_/fz003_ (ADR-009 punto 5). Con SQLSTATE visible: FZ001, FZ002, FZ003, 40P01 (interbloqueo)
sqle() { psql "$PGURL" -q -t -A -v VERBOSITY=sqlstate -c "$1" 2>&1 || true; }
# $1 = sentencia que retiene el bloqueo 2 s; $2 = cantidad; $3 = sentencia de cada sesión ({N} = su número); resultado en $TMP/r.N
en_paralelo_e() {
  psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; $1; select pg_sleep(2); commit;" > /dev/null &
  sleep 0.7
  for n in $(seq 1 "$2"); do sqle "${3//\{N\}/$n}" > "$TMP/r.$n" & done
  wait
}
# $1 = cantidad; $2 = sentencia de cada sesión ({N} = su número): todas a la vez, SIN bloqueador previo
a_la_vez_e() {
  for n in $(seq 1 "$1"); do sqle "${2//\{N\}/$n}" > "$TMP/r.$n" & done
  wait
}
K1='00000000-0000-4000-8000-0000000019b1'; K2='00000000-0000-4000-8000-0000000019b2'
sql "insert into public.users(id, email) values ('$K1','cta_k1@x.test'),('$K2','cta_k2@x.test')" > /dev/null
nueva_cuenta() { sql "insert into public.cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values ('$1','$2','$3','efectivo',$4)" > /dev/null; }
GASTO100() { echo "insert into public.transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values ('$K1', 100, current_date, 'gasto', '$1') returning 'ok'"; }

# INV-048 / REQ-N-023: 30 INSERT simultáneos de 100 sobre saldo 1000 -> exactamente 10 guardados, 20 FZ001, 0 interbloqueos, saldo 0
CA='00000000-0000-4000-8000-0000000019d1'
nueva_cuenta "$CA" "$K1" "Conc A" 1000
rm -f "$TMP"/r.*
en_paralelo_e "select 1 from public.cuentas where id = '$CA' for update" 30 "$(GASTO100 $CA)"
esperar "30 gastos simultáneos de 100 sobre 1000: guardados" "$(cuenta ok)" 10
esperar "30 gastos simultáneos: rechazos FZ001" "$(cuenta 'ERROR:  FZ001')" 20
esperar "30 gastos simultáneos: interbloqueos 40P01" "$(cuenta 'ERROR:  40P01')" 0
esperar "30 gastos simultáneos: filas y saldo final" "$(sql "select count(*) || '/' || public.cuenta_saldo_actual('$CA') from public.transacciones where cuenta_id = '$CA'")" "10/0.00"
# lo mismo SIN bloqueador previo (3 rondas con cuentas nuevas): las sesiones arrancan casi a la vez y compiten de verdad
for ronda in 1 2 3; do
  CR="00000000-0000-4000-8000-0000000019d$((1 + ronda))"
  nueva_cuenta "$CR" "$K1" "Conc ronda $ronda" 1000
  rm -f "$TMP"/r.*
  a_la_vez_e 30 "$(GASTO100 $CR)"
  esperar "ronda $ronda sin bloqueador: guardados" "$(cuenta ok)" 10
  esperar "ronda $ronda sin bloqueador: FZ001" "$(cuenta 'ERROR:  FZ001')" 20
  esperar "ronda $ronda sin bloqueador: 40P01" "$(cuenta 'ERROR:  40P01')" 0
  esperar "ronda $ronda sin bloqueador: saldo final" "$(sql "select public.cuenta_saldo_actual('$CR')")" "0.00"
done

# Ediciones e inserciones simultáneas: saldo 500 de holgura, 10 ediciones (+50) y 10 inserciones (50) -> exactamente 10 pasan
CE='00000000-0000-4000-8000-0000000019e1'
nueva_cuenta "$CE" "$K1" "Conc edicion" 0
sql "insert into public.transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values ('$K1', 1000, current_date, 'ingreso', '$CE')" > /dev/null
sql "insert into public.transacciones(id, usuario_id, monto, fecha, tipo, cuenta_id) select ('00000000-0000-4000-8000-00000019ed' || lpad(g::text, 2, '0'))::uuid, '$K1', 50, current_date, 'gasto', '$CE' from generate_series(1, 10) g" > /dev/null
rm -f "$TMP"/r.*
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; select 1 from public.cuentas where id = '$CE' for update; select pg_sleep(2); commit;" > /dev/null &
sleep 0.7
for n in $(seq 1 10); do
  sqle "update public.transacciones set monto = 100 where id = ('00000000-0000-4000-8000-00000019ed' || lpad('$n', 2, '0'))::uuid returning 'ok'" > "$TMP/r.$n" &
  sqle "insert into public.transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values ('$K1', 50, current_date, 'gasto', '$CE') returning 'ok'" > "$TMP/r.$((n + 10))" &
done
wait
esperar "20 ediciones/inserciones simultáneas con holgura de 500: guardadas" "$(cuenta ok)" 10
esperar "20 ediciones/inserciones simultáneas: FZ001" "$(cuenta 'ERROR:  FZ001')" 10
esperar "20 ediciones/inserciones simultáneas: 40P01" "$(cuenta 'ERROR:  40P01')" 0
esperar "20 ediciones/inserciones simultáneas: saldo final" "$(sql "select public.cuenta_saldo_actual('$CE')")" "0.00"

# Eliminaciones simultáneas: 10 ingresos de 100, un gasto de 600 (holgura 400) -> solo 4 ingresos se pueden eliminar
CD='00000000-0000-4000-8000-0000000019f1'
nueva_cuenta "$CD" "$K1" "Conc baja" 0
sql "insert into public.transacciones(id, usuario_id, monto, fecha, tipo, cuenta_id) select ('00000000-0000-4000-8000-00000019dd' || lpad(g::text, 2, '0'))::uuid, '$K1', 100, current_date, 'ingreso', '$CD' from generate_series(1, 10) g" > /dev/null
sql "insert into public.transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values ('$K1', 600, current_date, 'gasto', '$CD')" > /dev/null
rm -f "$TMP"/r.*
en_paralelo_e "select 1 from public.cuentas where id = '$CD' for update" 10 "delete from public.transacciones where id = ('00000000-0000-4000-8000-00000019dd' || lpad('{N}', 2, '0'))::uuid returning 'ok'"
esperar "10 bajas simultáneas con holgura de 400: eliminadas" "$(cuenta ok)" 4
esperar "10 bajas simultáneas: FZ001" "$(cuenta 'ERROR:  FZ001')" 6
esperar "10 bajas simultáneas: 40P01" "$(cuenta 'ERROR:  40P01')" 0
esperar "10 bajas simultáneas: saldo final" "$(sql "select public.cuenta_saldo_actual('$CD')")" "0.00"

# Dos usuarios distintos no se bloquean entre sí: la cuenta de K1 está retenida 2 s y K2 registra de inmediato
CK2='00000000-0000-4000-8000-0000000019f2'
nueva_cuenta "$CK2" "$K2" "Otro usuario" 1000
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; select 1 from public.cuentas where id = '$CA' for update; select pg_sleep(2); commit;" > /dev/null &
sleep 0.7
T0=$(date +%s%N)
esperar "usuario distinto con la cuenta de otro retenida" "$(sqle "insert into public.transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values ('$K2', 100, current_date, 'gasto', '$CK2') returning 'ok'")" ok
MS=$(( ($(date +%s%N) - T0) / 1000000 ))
if [ "$MS" -gt 1200 ]; then echo "ERROR: un usuario esperó a otro ($MS ms)"; exit 1; fi
echo "OK: dos usuarios distintos no se bloquean ($MS ms)"
wait

# Archivar y registrar a la vez: el registro espera al archivado y, bajo el mismo bloqueo, ve FZ002 (nada queda en la cuenta archivada)
CF='00000000-0000-4000-8000-0000000019f3'
nueva_cuenta "$CF" "$K1" "Conc archivar" 1000
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; update public.cuentas set archivada = true where id = '$CF'; select pg_sleep(2); commit;" > /dev/null &
sleep 0.7
esperar "registrar mientras otra petición archiva" "$(sqle "insert into public.transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values ('$K1', 10, current_date, 'gasto', '$CF') returning 'ok'")" "ERROR:  FZ002"
wait
esperar "archivar y registrar a la vez: transacciones en la cuenta archivada" "$(sql "select count(*) from public.transacciones where cuenta_id = '$CF'")" 0

# Altas simultáneas de cuentas: 21 al mismo tiempo para un usuario sin cuentas -> 20 creadas, 1 FZ003
K3='00000000-0000-4000-8000-0000000019b3'
sql "insert into public.users(id, email) values ('$K3','cta_k3@x.test')" > /dev/null
rm -f "$TMP"/r.*
en_paralelo_e "select pg_advisory_xact_lock(hashtextextended('fz003_tope_cuentas:$K3', 0))" 21 "insert into public.cuentas(usuario_id, nombre, tipo) values ('$K3', 'Alta {N}', 'efectivo') returning 'ok'"
esperar "21 altas simultáneas: creadas" "$(cuenta ok)" 20
esperar "21 altas simultáneas: FZ003" "$(cuenta 'ERROR:  FZ003')" 1
esperar "21 altas simultáneas: cuentas del usuario" "$(sql "select count(*) from public.cuentas where usuario_id = '$K3'")" 20
# y sin bloqueador previo: 10 existentes + 25 simultáneas -> 10 creadas, 15 FZ003
K4='00000000-0000-4000-8000-0000000019b4'
sql "insert into public.users(id, email) values ('$K4','cta_k4@x.test')" > /dev/null
sql "insert into public.cuentas(usuario_id, nombre, tipo) select '$K4', 'Previa ' || g, 'efectivo' from generate_series(1, 10) g" > /dev/null
rm -f "$TMP"/r.*
a_la_vez_e 25 "insert into public.cuentas(usuario_id, nombre, tipo) values ('$K4', 'Alta {N}', 'efectivo') returning 'ok'"
esperar "25 altas simultáneas con 10 previas: creadas" "$(cuenta ok)" 10
esperar "25 altas simultáneas con 10 previas: FZ003" "$(cuenta 'ERROR:  FZ003')" 15
esperar "25 altas simultáneas con 10 previas: cuentas" "$(sql "select count(*) from public.cuentas where usuario_id = '$K4'")" 20

# Limpieza: borrar los usuarios borra sus cuentas y transacciones (cascada) sin FZ001 ni interbloqueos
sql "delete from public.users where email like 'cta\_k%@x.test'" > /dev/null
esperar "limpieza por cascada: cuentas restantes" "$(sql "select count(*) from public.cuentas")" 0
echo "OK: concurrencia real de las cuentas de dinero"

# CHG-024 (fase b de CHG-019): transferencias entre cuentas de dinero (dos veces para comprobar que se puede repetir).
# Después de las cuentas: usa la tabla `cuentas`, las funciones de saldo de la fase (a) y los ayudantes de concurrencia de arriba.
run ../2026-11-25_transferencias.sql
run ../2026-11-25_transferencias.sql
PGOPTIONS="" psql "$PGURL" -q -v ON_ERROR_STOP=1 -f 09_comprobar_transferencias.sql
T1='00000000-0000-4000-8000-0000000025b1'
sql "insert into public.users(id, email) values ('$T1','trf_k1@x.test')" > /dev/null
TRF() { echo "insert into public.transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values ('$T1', '$1', '$2', $3, current_date) returning 'ok'"; }
SUMA() { sql "select coalesce(sum(saldo), 0) from public.cuentas_con_saldo('$T1')"; }

# INV-048/049: 20 transferencias simultáneas de 100 desde una cuenta con saldo 500 -> exactamente 5 guardadas, 15 FZ001, 0 interbloqueos
TA='00000000-0000-4000-8000-0000000025a1'; TB='00000000-0000-4000-8000-0000000025a2'
nueva_cuenta "$TA" "$T1" "Trf A" 500
nueva_cuenta "$TB" "$T1" "Trf B" 0
rm -f "$TMP"/r.*
en_paralelo_e "select 1 from public.cuentas where id = '$TA' for update" 20 "$(TRF $TA $TB 100)"
esperar "20 transferencias simultáneas de 100 sobre 500: guardadas" "$(cuenta ok)" 5
esperar "20 transferencias simultáneas: rechazos FZ001" "$(cuenta 'ERROR:  FZ001')" 15
esperar "20 transferencias simultáneas: interbloqueos 40P01" "$(cuenta 'ERROR:  40P01')" 0
esperar "20 transferencias simultáneas: saldos finales y suma" "$(sql "select public.cuenta_saldo_actual('$TA') || '/' || public.cuenta_saldo_actual('$TB')")/$(SUMA)" "0.00/500.00/500.00"
# lo mismo SIN bloqueador previo (3 rondas): las sesiones arrancan casi a la vez y compiten de verdad
for ronda in 1 2 3; do
  RA="00000000-0000-4000-8000-0000000025a$((2 + ronda * 2))"; RB="00000000-0000-4000-8000-0000000025a$((3 + ronda * 2))"
  nueva_cuenta "$RA" "$T1" "Trf ronda $ronda A" 500
  nueva_cuenta "$RB" "$T1" "Trf ronda $ronda B" 0
  rm -f "$TMP"/r.*
  a_la_vez_e 20 "$(TRF $RA $RB 100)"
  esperar "ronda $ronda de transferencias sin bloqueador: guardadas" "$(cuenta ok)" 5
  esperar "ronda $ronda de transferencias sin bloqueador: FZ001" "$(cuenta 'ERROR:  FZ001')" 15
  esperar "ronda $ronda de transferencias sin bloqueador: 40P01" "$(cuenta 'ERROR:  40P01')" 0
done

# ADR-009 punto 5: 20 A->B y 20 B->A simultáneas (cruzadas) con fondos de sobra -> las 40 se guardan, 0 interbloqueos, suma intacta
XA='00000000-0000-4000-8000-0000000025c1'; XB='00000000-0000-4000-8000-0000000025c2'
nueva_cuenta "$XA" "$T1" "Cruce A" 10000
nueva_cuenta "$XB" "$T1" "Cruce B" 10000
cruzadas() {   # $1 = retener el bloqueo de las dos cuentas 2 s antes (si) o no (no)
  rm -f "$TMP"/r.*
  if [ "$1" = si ]; then
    psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; select 1 from public.cuentas where id in ('$XA', '$XB') order by id for update; select pg_sleep(2); commit;" > /dev/null &
    sleep 0.7
  fi
  for n in $(seq 1 20); do
    sqle "$(TRF $XA $XB 10)" > "$TMP/r.$n" &
    sqle "$(TRF $XB $XA 10)" > "$TMP/r.$((n + 20))" &
  done
  wait
}
for ronda in 1 2 3; do
  ANTES="$(SUMA)"
  cruzadas no
  esperar "ronda $ronda de 20 A->B y 20 B->A simultáneas: guardadas" "$(cuenta ok)" 40
  esperar "ronda $ronda de 20 A->B y 20 B->A simultáneas: 40P01" "$(cuenta 'ERROR:  40P01')" 0
  esperar "ronda $ronda de 20 A->B y 20 B->A simultáneas: suma de saldos" "$(SUMA)" "$ANTES"
done
ANTES="$(SUMA)"
cruzadas si
esperar "20 A->B y 20 B->A con las cuentas retenidas: guardadas" "$(cuenta ok)" 40
esperar "20 A->B y 20 B->A con las cuentas retenidas: 40P01" "$(cuenta 'ERROR:  40P01')" 0
esperar "20 A->B y 20 B->A con las cuentas retenidas: suma de saldos" "$(SUMA)" "$ANTES"
esperar "20 A->B y 20 B->A: saldos finales (10 000 cada una)" "$(sql "select public.cuenta_saldo_actual('$XA') || '/' || public.cuenta_saldo_actual('$XB')")" "10000.00/10000.00"

# Bajas simultáneas: B recibe 10 transferencias de 100 y gasta 600 (holgura 400) -> solo 4 se pueden eliminar, 6 FZ001
BA='00000000-0000-4000-8000-0000000025d1'; BB='00000000-0000-4000-8000-0000000025d2'
nueva_cuenta "$BA" "$T1" "Baja A" 1000
nueva_cuenta "$BB" "$T1" "Baja B" 0
sql "insert into public.transferencias(id, usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) select ('00000000-0000-4000-8000-00000025dd' || lpad(g::text, 2, '0'))::uuid, '$T1', '$BA', '$BB', 100, current_date from generate_series(1, 10) g" > /dev/null
sql "insert into public.transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values ('$T1', 600, current_date, 'gasto', '$BB')" > /dev/null
rm -f "$TMP"/r.*
en_paralelo_e "select 1 from public.cuentas where id = '$BB' for update" 10 "delete from public.transferencias where id = ('00000000-0000-4000-8000-00000025dd' || lpad('{N}', 2, '0'))::uuid returning 'ok'"
esperar "10 bajas simultáneas de transferencias con holgura de 400: eliminadas" "$(cuenta ok)" 4
esperar "10 bajas simultáneas de transferencias: FZ001" "$(cuenta 'ERROR:  FZ001')" 6
esperar "10 bajas simultáneas de transferencias: 40P01" "$(cuenta 'ERROR:  40P01')" 0
esperar "10 bajas simultáneas de transferencias: saldo del destino" "$(sql "select public.cuenta_saldo_actual('$BB')")" "0.00"
# eliminar una transferencia que dejaría el destino negativo -> FZ001 (sesión suelta) y una cuenta con transferencias no se elimina
RESTANTE="$(sql "select id from public.transferencias where cuenta_destino_id = '$BB' limit 1")"
esperar "eliminar una transferencia que deja el destino negativo" "$(sqle "delete from public.transferencias where id = '$RESTANTE' returning 'ok'")" "ERROR:  FZ001"
esperar "eliminar una cuenta con transferencias (23503)" "$(sqle "delete from public.cuentas where id = '$BB'")" "ERROR:  23503"

# Dos usuarios distintos no se bloquean entre sí al transferir
T2='00000000-0000-4000-8000-0000000025b2'; UA='00000000-0000-4000-8000-0000000025e1'; UB='00000000-0000-4000-8000-0000000025e2'
sql "insert into public.users(id, email) values ('$T2','trf_k2@x.test')" > /dev/null
sql "insert into public.cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values ('$UA','$T2','Otro A','efectivo',1000),('$UB','$T2','Otro B','efectivo',0)" > /dev/null
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; select 1 from public.cuentas where id = '$XA' for update; select pg_sleep(2); commit;" > /dev/null &
sleep 0.7
T0=$(date +%s%N)
esperar "transferir con otro usuario reteniendo una cuenta ajena" "$(sqle "insert into public.transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values ('$T2', '$UA', '$UB', 100, current_date) returning 'ok'")" ok
MS=$(( ($(date +%s%N) - T0) / 1000000 ))
if [ "$MS" -gt 1200 ]; then echo "ERROR: un usuario esperó a otro al transferir ($MS ms)"; exit 1; fi
echo "OK: dos usuarios distintos no se bloquean al transferir ($MS ms)"
wait

# Archivar y transferir a la vez: la transferencia espera al archivado y, bajo el mismo bloqueo, ve FZ002
AR1='00000000-0000-4000-8000-0000000025f1'; AR2='00000000-0000-4000-8000-0000000025f2'
nueva_cuenta "$AR1" "$T1" "Trf archivar 1" 1000
nueva_cuenta "$AR2" "$T1" "Trf archivar 2" 0
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; update public.cuentas set archivada = true where id = '$AR2'; select pg_sleep(2); commit;" > /dev/null &
sleep 0.7
esperar "transferir mientras otra petición archiva el destino" "$(sqle "$(TRF $AR1 $AR2 10)")" "ERROR:  FZ002"
wait
esperar "archivar y transferir a la vez: transferencias de la cuenta archivada" "$(sql "select count(*) from public.transferencias where cuenta_destino_id = '$AR2'")" 0

# Limpieza: borrar los usuarios borra sus cuentas, transacciones y transferencias (cascada) sin FZ001/FZ002 ni interbloqueos
sql "delete from public.users where email like 'trf\_k%@x.test'" > /dev/null
esperar "limpieza por cascada: transferencias restantes" "$(sql "select count(*) from public.transferencias")" 0
esperar "limpieza por cascada: cuentas restantes" "$(sql "select count(*) from public.cuentas")" 0
echo "OK: concurrencia real de las transferencias entre cuentas"

# CHG-025 (fase c de CHG-019): integración de las cuentas con metas y recurrentes (dos veces para comprobar que se puede repetir).
# Se parte de la función de abono anterior (como en producción) para comprobar que la migración la reemplaza sin dejar dos firmas.
run ../2026-11-22_abonar_meta_atomico.sql
run ../2026-11-25_cuentas_integracion.sql
run ../2026-11-25_cuentas_integracion.sql
PGOPTIONS="" psql "$PGURL" -q -v ON_ERROR_STOP=1 -f 10_comprobar_cuentas_integracion.sql
I1='00000000-0000-4000-8000-0000000025c0'
sql "insert into public.users(id, email) values ('$I1','ci_k1@x.test')" > /dev/null
ABONO() { echo "select 'ok' from public.abonar_meta('$1', '$I1', 100, current_date, 'Abono', '$2')"; }
CONF() { echo "select 'ok' from public.confirmar_recurrente('$I1', '$1', '2026-12-05', '2027-01-05', null, null, null, false)"; }
nueva_meta() { sql "insert into public.metas(id, usuario_id, nombre, monto_objetivo) values ('$1','$I1','$2',100000)" > /dev/null; }
nueva_rec() { sql "insert into public.recurrentes(id, usuario_id, tipo, monto, descripcion, frecuencia, dia_ancla, proxima_fecha, cuenta_id) values ('$1','$I1','gasto',100,'Rec','mensual',5,'2026-12-05',$([ -n "${2:-}" ] && echo "'$2'" || echo null))" > /dev/null; }

# ADR-009 punto 13: 2 confirmaciones simultáneas de la MISMA ocurrencia -> exactamente 1 transacción, 1 ocurrencia_cambiada (P0001)
CC='00000000-0000-4000-8000-0000000025c1'; RC1='00000000-0000-4000-8000-0000000025c2'
nueva_cuenta "$CC" "$I1" "Conf A" 1000
nueva_rec "$RC1" "$CC"
rm -f "$TMP"/r.*
en_paralelo_e "select 1 from public.recurrentes where id = '$RC1' for update" 2 "$(CONF $RC1)"
esperar "2 confirmaciones simultáneas de la misma ocurrencia: confirmadas" "$(cuenta ok)" 1
esperar "2 confirmaciones simultáneas: rechazadas ocurrencia_cambiada (P0001)" "$(cuenta 'ERROR:  P0001')" 1
esperar "2 confirmaciones simultáneas: transacciones, fecha y saldo" "$(sql "select (select count(*) from public.transacciones where cuenta_id = '$CC') || '/' || (select proxima_fecha from public.recurrentes where id = '$RC1') || '/' || public.cuenta_saldo_actual('$CC')")" "1/2027-01-05/900.00"
# lo mismo con 12 sesiones y SIN bloqueador previo (3 rondas)
for ronda in 1 2 3; do
  RR="00000000-0000-4000-8000-0000000025c$((2 + ronda))"
  nueva_rec "$RR" "$CC"
  rm -f "$TMP"/r.*
  a_la_vez_e 12 "$(CONF $RR)"
  esperar "ronda $ronda de 12 confirmaciones simultáneas sin bloqueador: confirmadas" "$(cuenta ok)" 1
  esperar "ronda $ronda de 12 confirmaciones simultáneas: P0001" "$(cuenta 'ERROR:  P0001')" 11
  esperar "ronda $ronda de 12 confirmaciones simultáneas: transacciones" "$(sql "select count(*) from public.transacciones where cuenta_id = '$CC' and descripcion = 'Rec'")" "$((1 + ronda))"
done

# INV-048/052: 12 abonos simultáneos de 100 a una meta desde una cuenta con saldo 500 -> exactamente 5 guardados, 7 FZ001, 0 interbloqueos,
# y la meta suma SOLO lo que se descontó
CB='00000000-0000-4000-8000-0000000025d1'; MB='00000000-0000-4000-8000-0000000025d2'
nueva_cuenta "$CB" "$I1" "Abono A" 500
nueva_meta "$MB" "Abonos"
rm -f "$TMP"/r.*
en_paralelo_e "select 1 from public.cuentas where id = '$CB' for update" 12 "$(ABONO $MB $CB)"
esperar "12 abonos simultáneos de 100 sobre 500: guardados" "$(cuenta ok)" 5
esperar "12 abonos simultáneos: rechazos FZ001" "$(cuenta 'ERROR:  FZ001')" 7
esperar "12 abonos simultáneos: interbloqueos 40P01" "$(cuenta 'ERROR:  40P01')" 0
esperar "12 abonos simultáneos: meta, saldo y transacciones" "$(sql "select (select monto_actual from public.metas where id = '$MB') || '/' || public.cuenta_saldo_actual('$CB') || '/' || (select count(*) from public.transacciones where cuenta_id = '$CB')")" "500/0.00/5"
# lo mismo SIN bloqueador previo (3 rondas) y con metas distintas
for ronda in 1 2 3; do
  RB="00000000-0000-4000-8000-0000000025d$((2 + ronda * 2))"; RM="00000000-0000-4000-8000-0000000025d$((3 + ronda * 2))"
  nueva_cuenta "$RB" "$I1" "Abono ronda $ronda" 500
  nueva_meta "$RM" "Abonos ronda $ronda"
  rm -f "$TMP"/r.*
  a_la_vez_e 12 "$(ABONO $RM $RB)"
  esperar "ronda $ronda de abonos sin bloqueador: guardados" "$(cuenta ok)" 5
  esperar "ronda $ronda de abonos sin bloqueador: FZ001" "$(cuenta 'ERROR:  FZ001')" 7
  esperar "ronda $ronda de abonos sin bloqueador: 40P01" "$(cuenta 'ERROR:  40P01')" 0
  esperar "ronda $ronda de abonos sin bloqueador: meta" "$(sql "select monto_actual from public.metas where id = '$RM'")" 500
done

# Abonos + confirmaciones (recurrentes distintas) + gastos sueltos a la vez sobre la MISMA cuenta con saldo para 10 de 30:
# exactamente 10 pasan, 20 FZ001, 0 interbloqueos; cada recurrente con la fecha movida tiene su transacción y las rechazadas no la movieron
CM='00000000-0000-4000-8000-0000000025e1'; MM='00000000-0000-4000-8000-0000000025e2'
nueva_cuenta "$CM" "$I1" "Mezcla" 1000
nueva_meta "$MM" "Mezcla"
RECS=()
for k in 1 2 3 4 5 6 7 8; do R="00000000-0000-4000-8000-0000000025e$(printf %x $((2 + k)))"; RECS+=("$R"); nueva_rec "$R" "$CM"; done
rm -f "$TMP"/r.*
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; select 1 from public.cuentas where id = '$CM' for update; select pg_sleep(2); commit;" > /dev/null &
sleep 0.7
for n in $(seq 1 30); do
  if [ "$n" -le 12 ]; then S="$(ABONO $MM $CM)"
  elif [ "$n" -le 20 ]; then S="$(CONF "${RECS[$((n - 13))]}")"
  else S="insert into public.transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values ('$I1', 100, current_date, 'gasto', '$CM') returning 'ok'"; fi
  sqle "$S" > "$TMP/r.$n" &
done
wait
esperar "abonos + confirmaciones + gastos sobre 1000: guardados" "$(cuenta ok)" 10
esperar "abonos + confirmaciones + gastos: FZ001" "$(cuenta 'ERROR:  FZ001')" 20
esperar "abonos + confirmaciones + gastos: interbloqueos 40P01" "$(cuenta 'ERROR:  40P01')" 0
esperar "abonos + confirmaciones + gastos: saldo final" "$(sql "select public.cuenta_saldo_actual('$CM')")" 0.00
esperar "abonos + confirmaciones: recurrentes con la fecha movida = transacciones de recurrentes" "$(sql "select (select count(*) from public.recurrentes where cuenta_id = '$CM' and proxima_fecha <> '2026-12-05') = (select count(*) from public.transacciones where cuenta_id = '$CM' and descripcion = 'Rec')")" t
esperar "abonos + confirmaciones: la meta suma lo abonado" "$(sql "select (select monto_actual from public.metas where id = '$MM') = 100 * (select count(*) from public.transacciones where cuenta_id = '$CM' and descripcion = 'Abono')")" t

# Dos usuarios distintos no se bloquean entre sí al confirmar
CU='00000000-0000-4000-8000-0000000025f1'; RU='00000000-0000-4000-8000-0000000025f2'
I2='00000000-0000-4000-8000-0000000025c9'
sql "insert into public.users(id, email) values ('$I2','ci_k2@x.test')" > /dev/null
sql "insert into public.recurrentes(id, usuario_id, tipo, monto, descripcion, frecuencia, dia_ancla, proxima_fecha) values ('$RU','$I2','gasto',10,'Rec','mensual',5,'2026-12-05')" > /dev/null
psql "$PGURL" -q -v ON_ERROR_STOP=1 -c "begin; select 1 from public.recurrentes where id = '$RC1' for update; select pg_sleep(2); commit;" > /dev/null &
sleep 0.5
T0=$(date +%s%N)
sql "select 'ok' from public.confirmar_recurrente('$I2', '$RU', '2026-12-05', '2027-01-05', null, null, null, false)" > /dev/null
MS=$(( ($(date +%s%N) - T0) / 1000000 ))
if [ "$MS" -gt 1200 ]; then echo "ERROR: un usuario esperó a otro al confirmar ($MS ms)"; exit 1; fi
echo "OK: dos usuarios distintos no se bloquean al confirmar ($MS ms)"
wait

# Limpieza: borrar los usuarios borra sus cuentas, metas, recurrentes y transacciones (cascada) sin FZ001/FZ002 ni interbloqueos
sql "delete from public.users where email like 'ci\_k%@x.test'" > /dev/null
esperar "limpieza por cascada: recurrentes con cuenta restantes" "$(sql "select count(*) from public.recurrentes where cuenta_id is not null")" 0
esperar "limpieza por cascada: cuentas restantes" "$(sql "select count(*) from public.cuentas")" 0
echo "OK: concurrencia real de la integración de las cuentas con metas y recurrentes"
