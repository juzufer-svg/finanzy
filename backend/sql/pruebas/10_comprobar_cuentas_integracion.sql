-- CHG-025 (fase c de CHG-019) · INV-008, INV-025, INV-026, INV-046 a INV-052: integración de cuentas con metas y recurrentes
-- (después de 2026-11-25_cuentas_integracion.sql, ejecutado dos veces). La concurrencia real está en probar.sh.
-- Se ejecuta desde backend/sql/pruebas (usa \ir con ruta relativa). Los usuarios de prueba tienen correo «ci_...@x.test» y se borran al final.

create function pg_temp.debe_fallar(p_sql text, p_estado text, p_nombre text, p_mensaje text default null) returns void language plpgsql as $$
declare v_fallo boolean := false; v_estado text; v_msg text;
begin
  begin
    execute p_sql;
  exception when others then
    v_fallo := true; v_estado := sqlstate; v_msg := sqlerrm;
  end;
  if not v_fallo then raise exception '% debía fallar con % y no falló', p_nombre, p_estado; end if;
  if v_estado <> p_estado then raise exception '% debía fallar con % y dio % (%)', p_nombre, p_estado, v_estado, v_msg; end if;
  if p_mensaje is not null and v_msg <> p_mensaje then raise exception '% debía dar el mensaje % y dio %', p_nombre, p_mensaje, v_msg; end if;
end $$;

-- 0. La migración se puede repetir sobre datos sin tocarlos (REQ-N-025)
do $$
declare u1 uuid := '00000000-0000-4000-8000-000000002501'; a uuid := '00000000-0000-4000-8000-0000000025a0';
begin
  insert into users(id, email) values (u1, 'ci_0@x.test');
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values (a, u1, 'A', 'efectivo', 100);
  insert into recurrentes(usuario_id, tipo, monto, frecuencia, dia_ancla, proxima_fecha, cuenta_id)
    values (u1, 'gasto', 10, 'mensual', 5, '2026-12-05', a);
  insert into metas(usuario_id, nombre, monto_objetivo, monto_actual) values (u1, 'M0', 100, 7);
end $$;
select count(*) as n_antes, coalesce(sum(monto), 0) as suma_antes,
       (select count(*) from public.recurrentes where cuenta_id is not null) as rc_antes,
       (select coalesce(sum(monto_actual), 0) from public.metas) as metas_antes from public.transacciones \gset
\ir ../2026-11-25_cuentas_integracion.sql
select count(*) as n_despues, coalesce(sum(monto), 0) as suma_despues,
       (select count(*) from public.recurrentes where cuenta_id is not null) as rc_despues,
       (select coalesce(sum(monto_actual), 0) from public.metas) as metas_despues from public.transacciones \gset
select (:n_antes <> :n_despues or :suma_antes <> :suma_despues or :rc_antes <> :rc_despues or :metas_antes <> :metas_despues) as cambio \gset
\if :cambio
  \echo ERROR: la migración cambió transacciones, recurrentes o metas existentes
  select 1 / 0;
\endif
\echo OK: la migración se repite sobre datos sin tocar transacciones, recurrentes ni metas
delete from users where email = 'ci_0@x.test';

-- 1. Estructura y permisos (INV-021, INV-046, INV-052)
do $$
declare n bigint; f text; cols text;
  funciones text[] := array['public.abonar_meta(uuid, uuid, numeric, date, text, uuid)',
    'public.confirmar_recurrente(uuid, uuid, date, date, numeric, date, uuid, boolean)'];
begin
  select count(*) into n from information_schema.columns
   where table_schema = 'public' and table_name = 'recurrentes' and column_name = 'cuenta_id' and data_type = 'uuid' and is_nullable = 'YES';
  if n <> 1 then raise exception 'recurrentes.cuenta_id debe ser uuid nullable'; end if;
  select count(*) into n from pg_constraint c
   where c.conrelid = 'public.recurrentes'::regclass and c.contype = 'f' and c.confrelid = 'public.cuentas'::regclass
     and c.confdeltype = 'a' and array_length(c.conkey, 1) = 2
     and (select string_agg(a.attname, ',' order by k.ord) from unnest(c.conkey) with ordinality k(attnum, ord)
            join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k.attnum) = 'cuenta_id,usuario_id';
  if n <> 1 then raise exception 'falta la llave compuesta (cuenta_id, usuario_id) NO ACTION en recurrentes (hay %)', n; end if;
  select count(*) into n from pg_indexes where schemaname = 'public' and tablename = 'recurrentes' and indexname = 'idx_recurrentes_cuenta'
     and indexdef like '%(cuenta_id)%WHERE (cuenta_id IS NOT NULL)%';
  if n <> 1 then raise exception 'falta el índice parcial idx_recurrentes_cuenta'; end if;
  -- una sola firma de abonar_meta (la anterior se eliminó) y una de confirmar_recurrente
  select count(*) into n from pg_proc where pronamespace = 'public'::regnamespace and proname = 'abonar_meta';
  if n <> 1 then raise exception 'debe haber una sola abonar_meta (hay %)', n; end if;
  select count(*) into n from pg_proc where pronamespace = 'public'::regnamespace and proname = 'confirmar_recurrente';
  if n <> 1 then raise exception 'debe haber una sola confirmar_recurrente (hay %)', n; end if;
  select array_to_string(proargnames, ',') into cols from pg_proc where oid = to_regprocedure(funciones[1]);
  if cols <> 'p_meta_id,p_usuario_id,p_monto,p_fecha,p_descripcion,p_cuenta_id' then raise exception 'parámetros de abonar_meta: %', cols; end if;
  select array_to_string(proargnames, ',') into cols from pg_proc where oid = to_regprocedure(funciones[2]);
  if cols <> 'p_usuario_id,p_recurrente_id,p_ocurrencia,p_siguiente,p_monto,p_fecha,p_cuenta_id,p_cuenta_indicada' then
    raise exception 'parámetros de confirmar_recurrente: %', cols;
  end if;
  foreach f in array funciones loop
    if has_function_privilege('anon', f, 'execute') or has_function_privilege('authenticated', f, 'execute') then
      raise exception 'anon/authenticated pueden ejecutar %', f;
    end if;
    select count(*) into n from pg_proc p, aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
     where p.oid = to_regprocedure(f) and a.grantee = 0 and a.privilege_type = 'EXECUTE';
    if n <> 0 then raise exception 'PUBLIC puede ejecutar %', f; end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') and not has_function_privilege('service_role', f, 'execute') then
      raise exception 'service_role no puede ejecutar %', f;
    end if;
    select count(*) into n from pg_proc p where p.oid = to_regprocedure(f) and not p.prosecdef
       and exists (select 1 from unnest(p.proconfig) c where c like 'search_path=%');
    if n <> 1 then raise exception '% debe ser SECURITY INVOKER con search_path fijo', f; end if;
  end loop;
  raise notice 'OK: INV-021/046/052 columna, llave compuesta NO ACTION, índice, una sola firma, parámetros y permisos';
end $$;

-- 2. Abonos con cuenta (INV-008, INV-048, INV-052)
do $$
declare u1 uuid := '00000000-0000-4000-8000-000000002511'; u2 uuid := '00000000-0000-4000-8000-000000002512';
  c1 uuid := '00000000-0000-4000-8000-0000000025c1'; carch uuid := '00000000-0000-4000-8000-0000000025c2';
  cajena uuid := '00000000-0000-4000-8000-0000000025c3'; ctar uuid := '00000000-0000-4000-8000-0000000025c4';
  m uuid; m2 uuid; n bigint; v numeric; r record;
begin
  insert into users(id, email) values (u1, 'ci_1@x.test'), (u2, 'ci_2@x.test');
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values
    (c1, u1, 'Efectivo', 'efectivo', 500), (carch, u1, 'Vieja', 'efectivo', 500), (cajena, u2, 'Ajena', 'efectivo', 500),
    (ctar, u1, 'Tarjeta', 'tarjeta_credito', 0);
  insert into metas(usuario_id, nombre, monto_objetivo) values (u1, 'Viaje', 1000) returning id into m;
  insert into metas(usuario_id, nombre, monto_objetivo) values (u1, 'Moto', 1000) returning id into m2;

  -- con cuenta: descuenta el saldo, suma a la meta y deja UNA transacción de gasto en esa cuenta
  select * into r from public.abonar_meta(m, u1, 200, current_date, 'Abono', c1);
  if r.monto_actual <> 200 then raise exception 'la meta debía quedar en 200 (%)', r.monto_actual; end if;
  if public.cuenta_saldo_actual(c1) <> 300 then raise exception 'el saldo debía ser 300 (%)', public.cuenta_saldo_actual(c1); end if;
  select count(*) into n from transacciones where usuario_id = u1 and cuenta_id = c1 and tipo = 'gasto' and monto = 200;
  if n <> 1 then raise exception 'debía haber 1 gasto de 200 en la cuenta (%)', n; end if;

  -- sin saldo: FZ001 y la meta NO cambia (ni transacción ni categoría nueva)
  perform pg_temp.debe_fallar(format('select * from public.abonar_meta(%L, %L, 400, current_date, ''x'', %L)', m, u1, c1), 'FZ001', 'abono sin saldo');
  select monto_actual into v from metas where id = m;
  if v <> 200 then raise exception 'la meta cambió tras un abono rechazado (%)', v; end if;
  if public.cuenta_saldo_actual(c1) <> 300 then raise exception 'el saldo cambió tras un abono rechazado'; end if;
  select count(*) into n from transacciones where usuario_id = u1;
  if n <> 1 then raise exception 'quedaron % transacciones tras un abono rechazado (esperada 1)', n; end if;
  -- saldo justo: se puede abonar todo
  perform public.abonar_meta(m, u1, 300, current_date, 'Todo', c1);
  if public.cuenta_saldo_actual(c1) <> 0 then raise exception 'el saldo debía quedar en 0'; end if;

  -- archivada: FZ002 y nada cambia
  update cuentas set archivada = true where id = carch;
  perform pg_temp.debe_fallar(format('select * from public.abonar_meta(%L, %L, 10, current_date, ''x'', %L)', m2, u1, carch), 'FZ002', 'abono con cuenta archivada');
  select monto_actual into v from metas where id = m2;
  if coalesce(v, 0) <> 0 then raise exception 'la meta cambió con la cuenta archivada (%)', v; end if;

  -- cuenta ajena: la llave compuesta la rechaza (23503) y nada cambia
  perform pg_temp.debe_fallar(format('select * from public.abonar_meta(%L, %L, 10, current_date, ''x'', %L)', m2, u1, cajena), '23503', 'abono con cuenta ajena');
  select monto_actual into v from metas where id = m2;
  if coalesce(v, 0) <> 0 then raise exception 'la meta cambió con una cuenta ajena (%)', v; end if;
  -- meta ajena: sigue rechazada (INV-001)
  perform pg_temp.debe_fallar(format('select * from public.abonar_meta(%L, %L, 10, current_date, ''x'', %L)', m2, u2, cajena), 'P0002', 'abono a meta ajena');

  -- la tarjeta de crédito sí puede quedar en negativo
  perform public.abonar_meta(m2, u1, 50, current_date, 'Con tarjeta', ctar);
  if public.cuenta_saldo_actual(ctar) <> -50 then raise exception 'la tarjeta debía quedar en -50'; end if;

  -- sin cuenta (llamada de 5 parámetros y con null): comportamiento de siempre, transacción sin cuenta
  select * into r from public.abonar_meta(m2, u1, 25, current_date, 'Sin cuenta');
  if r.monto_actual <> 75 then raise exception 'la meta debía quedar en 75 (%)', r.monto_actual; end if;
  select * into r from public.abonar_meta(m2, u1, 5, current_date, 'Con null', null);
  select count(*) into n from transacciones where usuario_id = u1 and cuenta_id is null and monto in (25, 5);
  if n <> 2 then raise exception 'los abonos sin cuenta debían quedar sin cuenta (%)', n; end if;
  perform pg_temp.debe_fallar(format('select * from public.abonar_meta(%L, %L, 0, current_date, ''x'', %L)', m2, u1, c1), '22023', 'abono con monto 0');
  raise notice 'OK: INV-008/048/052 abono con cuenta (saldo, meta, FZ001, FZ002, ajena) y sin cuenta idéntico al anterior';
end $$;

-- 3. Confirmar recurrentes (INV-025, INV-026, INV-048, INV-052, ADR-009 punto 13)
do $$
declare u1 uuid := '00000000-0000-4000-8000-000000002521'; u2 uuid := '00000000-0000-4000-8000-000000002522';
  c1 uuid := '00000000-0000-4000-8000-0000000025d1'; c2 uuid := '00000000-0000-4000-8000-0000000025d2';
  carch uuid := '00000000-0000-4000-8000-0000000025d3'; cajena uuid := '00000000-0000-4000-8000-0000000025d4';
  cat uuid := '00000000-0000-4000-8000-0000000025e1';
  rc uuid; rsin uuid; rarch uuid; rajena uuid; rpaus uuid; t record; n bigint; f date;
begin
  insert into users(id, email) values (u1, 'ci_3@x.test'), (u2, 'ci_4@x.test');
  insert into categorias(id, usuario_id, nombre, tipo) values (cat, u1, 'Casa', 'gasto');
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values
    (c1, u1, 'Principal', 'efectivo', 300), (c2, u1, 'Otra', 'efectivo', 1000), (carch, u1, 'Vieja', 'efectivo', 1000), (cajena, u2, 'Ajena', 'efectivo', 1000);
  insert into recurrentes(usuario_id, categoria_id, tipo, monto, descripcion, medio_pago, frecuencia, dia_ancla, proxima_fecha, cuenta_id)
    values (u1, cat, 'gasto', 120, 'Arriendo', 'debito', 'mensual', 5, '2026-12-05', c1) returning id into rc;
  insert into recurrentes(usuario_id, tipo, monto, frecuencia, dia_ancla, proxima_fecha) values (u1, 'gasto', 50, 'mensual', 5, '2026-12-05') returning id into rsin;
  insert into recurrentes(usuario_id, tipo, monto, frecuencia, dia_ancla, proxima_fecha, cuenta_id)
    values (u1, 'gasto', 10, 'mensual', 5, '2026-12-05', carch) returning id into rarch;
  insert into recurrentes(usuario_id, tipo, monto, frecuencia, dia_ancla, proxima_fecha, activa) values (u1, 'gasto', 10, 'mensual', 5, '2026-12-05', false) returning id into rpaus;
  insert into recurrentes(usuario_id, tipo, monto, frecuencia, dia_ancla, proxima_fecha) values (u2, 'gasto', 10, 'mensual', 5, '2026-12-05') returning id into rajena;
  update cuentas set archivada = true where id = carch;

  -- con la cuenta de la plantilla: crea la transacción con los datos de la plantilla, en esa cuenta, y avanza la fecha
  select * into t from public.confirmar_recurrente(u1, rc, '2026-12-05', '2027-01-05', null, null, null, false);
  if t.cuenta_id is distinct from c1 or t.monto <> 120 or t.descripcion <> 'Arriendo' or t.medio_pago <> 'debito'
     or t.categoria_id is distinct from cat or t.tipo <> 'gasto' or t.fecha <> '2026-12-05' or t.usuario_id <> u1 then
    raise exception 'la transacción creada no coincide con la plantilla: %', t;
  end if;
  select proxima_fecha into f from recurrentes where id = rc;
  if f <> '2027-01-05' then raise exception 'la fecha debía avanzar a 2027-01-05 (%)', f; end if;
  if public.cuenta_saldo_actual(c1) <> 180 then raise exception 'el saldo debía ser 180 (%)', public.cuenta_saldo_actual(c1); end if;

  -- misma ocurrencia otra vez: ocurrencia_cambiada y NO se crea nada
  perform pg_temp.debe_fallar(format('select * from public.confirmar_recurrente(%L, %L, ''2026-12-05'', ''2027-01-05'', null, null, null, false)', u1, rc),
    'P0001', 'confirmar dos veces la misma ocurrencia', 'ocurrencia_cambiada');
  select count(*) into n from transacciones where usuario_id = u1 and descripcion = 'Arriendo';
  if n <> 1 then raise exception 'debía haber 1 transacción de Arriendo (%)', n; end if;

  -- sin saldo (monto ajustado 500 > 180): FZ001 y la fecha NO avanza
  perform pg_temp.debe_fallar(format('select * from public.confirmar_recurrente(%L, %L, ''2027-01-05'', ''2027-02-05'', 500, null, null, false)', u1, rc), 'FZ001', 'confirmar sin saldo');
  select proxima_fecha into f from recurrentes where id = rc;
  if f <> '2027-01-05' then raise exception 'la fecha avanzó pese a FZ001 (%)', f; end if;
  select count(*) into n from transacciones where usuario_id = u1 and descripcion = 'Arriendo';
  if n <> 1 then raise exception 'se creó una transacción pese a FZ001'; end if;

  -- cuenta archivada: FZ002 y la fecha NO avanza
  perform pg_temp.debe_fallar(format('select * from public.confirmar_recurrente(%L, %L, ''2026-12-05'', ''2027-01-05'', null, null, null, false)', u1, rarch), 'FZ002', 'confirmar con cuenta archivada');
  select proxima_fecha into f from recurrentes where id = rarch;
  if f <> '2026-12-05' then raise exception 'la fecha avanzó pese a FZ002 (%)', f; end if;

  -- ocurrencia distinta de la pendiente: ocurrencia_cambiada; pausada: también; nada cambia
  perform pg_temp.debe_fallar(format('select * from public.confirmar_recurrente(%L, %L, ''2026-11-05'', ''2026-12-05'', null, null, null, false)', u1, rsin), 'P0001', 'confirmar otra ocurrencia', 'ocurrencia_cambiada');
  perform pg_temp.debe_fallar(format('select * from public.confirmar_recurrente(%L, %L, ''2026-12-05'', ''2027-01-05'', null, null, null, false)', u1, rpaus), 'P0001', 'confirmar una pausada', 'ocurrencia_cambiada');
  select count(*) into n from recurrentes where id in (rsin, rpaus) and proxima_fecha <> '2026-12-05';
  if n <> 0 then raise exception 'una confirmación rechazada movió la fecha'; end if;

  -- recurrente de otro usuario (INV-001) o inexistente: P0002
  perform pg_temp.debe_fallar(format('select * from public.confirmar_recurrente(%L, %L, ''2026-12-05'', ''2027-01-05'', null, null, null, false)', u1, rajena), 'P0002', 'confirmar recurrente ajena');
  perform pg_temp.debe_fallar(format('select * from public.confirmar_recurrente(%L, %L, ''2026-12-05'', ''2027-01-05'', null, null, null, false)', u1, gen_random_uuid()), 'P0002', 'confirmar inexistente');

  -- cuenta indicada distinta de la plantilla; fecha y monto ajustados
  select * into t from public.confirmar_recurrente(u1, rc, '2027-01-05', '2027-02-05', 30, '2027-01-07', c2, true);
  if t.cuenta_id is distinct from c2 or t.monto <> 30 or t.fecha <> '2027-01-07' then raise exception 'la cuenta indicada no se respetó: %', t; end if;
  -- cuenta indicada = null: sin cuenta (aunque la plantilla tenga una)
  select * into t from public.confirmar_recurrente(u1, rc, '2027-02-05', '2027-03-05', null, null, null, true);
  if t.cuenta_id is not null then raise exception 'p_cuenta_indicada = true con null debía crear la transacción sin cuenta: %', t; end if;
  -- plantilla sin cuenta + cuenta indicada
  select * into t from public.confirmar_recurrente(u1, rsin, '2026-12-05', '2027-01-05', null, null, c2, true);
  if t.cuenta_id is distinct from c2 then raise exception 'la cuenta indicada sobre plantilla sin cuenta no se respetó'; end if;
  -- cuenta indicada ajena: 23503 y la fecha NO avanza
  perform pg_temp.debe_fallar(format('select * from public.confirmar_recurrente(%L, %L, ''2027-01-05'', ''2027-02-05'', null, null, %L, true)', u1, rsin, cajena), '23503', 'confirmar con cuenta ajena');
  select proxima_fecha into f from recurrentes where id = rsin;
  if f <> '2027-01-05' then raise exception 'la fecha avanzó pese a la cuenta ajena (%)', f; end if;
  -- valores inválidos
  perform pg_temp.debe_fallar(format('select * from public.confirmar_recurrente(%L, %L, ''2027-01-05'', ''2027-02-05'', 0, null, null, false)', u1, rsin), '22023', 'confirmar con monto 0');
  perform pg_temp.debe_fallar(format('select * from public.confirmar_recurrente(%L, %L, ''2027-01-05'', ''2027-01-05'', null, null, null, false)', u1, rsin), '22023', 'siguiente no posterior');

  -- borrar una cuenta con recurrentes asignadas: 23503 (se archiva, INV-050); al desasignarla ya se puede borrar
  perform pg_temp.debe_fallar(format('delete from cuentas where id = %L', c1), '23503', 'borrar cuenta con recurrentes asignadas');
  update cuentas set archivada = true where id = c1;
  update recurrentes set cuenta_id = null where cuenta_id = carch;  -- sin movimientos y sin asignaciones, borrar es posible
  delete from cuentas where id = carch;
  raise notice 'OK: INV-025/026/048/052 confirmar_recurrente atómica (plantilla, cuenta, FZ001, FZ002, ocurrencia_cambiada, ajena) y borrar cuenta con recurrentes → 23503';
end $$;

-- Limpieza: los usuarios de prueba (la cascada borra sus cuentas, transacciones y recurrentes, sin FZ001/FZ002)
do $$ declare n bigint; begin
  delete from users where email like 'ci\_%@x.test';
  select (select count(*) from cuentas) + (select count(*) from recurrentes where cuenta_id is not null) into n;
  if n <> 0 then raise exception 'quedaron % filas tras borrar los usuarios de prueba', n; end if;
  raise notice 'OK: limpieza (cascada de usuarios con cuentas y recurrentes con cuenta)';
end $$;
