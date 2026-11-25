-- CHG-024 (fase b de CHG-019) · INV-046 a INV-051: transferencias (después de 2026-11-25_transferencias.sql, ejecutado dos veces)
-- La concurrencia real (sesiones simultáneas) está en probar.sh. Se ejecuta desde backend/sql/pruebas (usa \ir con ruta relativa).
-- Los usuarios de prueba tienen correo «trf_...@x.test» y se borran al final.

-- 0. La migración se puede repetir sobre datos sin tocarlos (REQ-N-025)
create function pg_temp.debe_fallar(p_sql text, p_estado text, p_nombre text) returns void language plpgsql as $$
declare v_fallo boolean := false; v_estado text;
begin
  begin
    execute p_sql;
  exception when others then
    v_fallo := true; v_estado := sqlstate;
  end;
  if not v_fallo then raise exception '% debía fallar con % y no falló', p_nombre, p_estado; end if;
  if v_estado <> p_estado then raise exception '% debía fallar con % y dio %', p_nombre, p_estado, v_estado; end if;
end $$;

do $$
declare u1 uuid := '00000000-0000-4000-8000-000000002401';
  a uuid := '00000000-0000-4000-8000-0000000024a1'; b uuid := '00000000-0000-4000-8000-0000000024a2';
begin
  insert into users(id, email) values (u1, 'trf_0@x.test');
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values (a, u1, 'A', 'efectivo', 100), (b, u1, 'B', 'efectivo', 0);
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (u1, a, b, 30, current_date);
end $$;
select count(*) as n_antes, coalesce(sum(monto), 0) as suma_antes from public.transferencias \gset
\ir ../2026-11-25_transferencias.sql
select count(*) as n_despues, coalesce(sum(monto), 0) as suma_despues from public.transferencias \gset
select (:n_antes <> :n_despues or :suma_antes <> :suma_despues) as cambio \gset
\if :cambio
  \echo ERROR: la migración cambió las transferencias existentes
  select 1 / 0;
\endif
\echo OK: la migración se repite sobre datos sin tocar las :n_antes transferencias existentes
delete from users where email = 'trf_0@x.test';

-- 1. RLS, privilegios, tabla, llaves, índices y disparador BEFORE (INV-021, INV-046, INV-048, INV-049)
do $$
declare n bigint; f text; cols text; r record;
  funciones text[] := array['public.cuenta_saldo_actual(uuid)', 'public.cuentas_con_saldo(uuid)', 'public.fz001_saldo_transferencias_fn()'];
begin
  select count(*) into n from pg_tables where schemaname = 'public' and tablename = 'transferencias' and rowsecurity;
  if n <> 1 then raise exception 'transferencias sin RLS'; end if;
  select count(*) into n from pg_policies where schemaname = 'public' and tablename = 'transferencias';
  if n <> 0 then raise exception 'transferencias no debe tener políticas (hay %)', n; end if;
  if has_table_privilege('anon', 'public.transferencias', 'select') or has_table_privilege('authenticated', 'public.transferencias', 'select')
     or has_table_privilege('anon', 'public.transferencias', 'insert,update,delete')
     or has_table_privilege('authenticated', 'public.transferencias', 'insert,update,delete') then
    raise exception 'anon/authenticated tienen acceso a transferencias';
  end if;
  select count(*) into n from pg_class c, aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
   where c.oid = 'public.transferencias'::regclass and a.grantee = 0;
  if n <> 0 then raise exception 'PUBLIC tiene privilegios sobre transferencias'; end if;
  if exists (select 1 from pg_roles where rolname = 'service_role')
     and not has_table_privilege('service_role', 'public.transferencias', 'select,insert,update,delete') then
    raise exception 'service_role no tiene acceso a transferencias';
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
  -- las funciones de saldo conservan firma, volatilidad y columnas de la fase (a)
  select count(*) into n from pg_proc where oid = to_regprocedure('public.cuentas_con_saldo(uuid)') and provolatile = 's';
  if n <> 1 then raise exception 'cuentas_con_saldo debe seguir siendo STABLE'; end if;
  select count(*) into n from pg_proc where oid = to_regprocedure('public.cuenta_saldo_actual(uuid)') and provolatile = 'v';
  if n <> 1 then raise exception 'cuenta_saldo_actual debe seguir siendo VOLATILE'; end if;
  select array_to_string(proargnames, ',') into cols from pg_proc where oid = to_regprocedure('public.cuentas_con_saldo(uuid)');
  if cols <> 'p_usuario_id,id,usuario_id,nombre,tipo,saldo_inicial,archivada,created_at,saldo' then
    raise exception 'columnas de cuentas_con_saldo fuera de la lista blanca: %', cols;
  end if;
  -- columnas de la tabla
  select string_agg(column_name || ':' || data_type || ':' || is_nullable, ',' order by column_name) into cols
    from information_schema.columns where table_schema = 'public' and table_name = 'transferencias';
  if cols is distinct from 'created_at:timestamp with time zone:NO,cuenta_destino_id:uuid:NO,cuenta_origen_id:uuid:NO,descripcion:character varying:YES,fecha:date:NO,id:uuid:NO,monto:numeric:NO,usuario_id:uuid:NO' then
    raise exception 'columnas de transferencias: %', cols;
  end if;
  select count(*) into n from information_schema.columns
   where table_schema = 'public' and table_name = 'transferencias' and column_name = 'monto' and numeric_precision = 12 and numeric_scale = 2;
  if n <> 1 then raise exception 'monto debe ser NUMERIC(12,2)'; end if;
  select count(*) into n from information_schema.columns
   where table_schema = 'public' and table_name = 'transferencias' and column_name = 'descripcion' and character_maximum_length = 255;
  if n <> 1 then raise exception 'descripcion debe ser varchar(255)'; end if;
  -- llaves compuestas (cuenta, usuario_id) NO ACTION (no RESTRICT) y usuario CASCADE
  select count(*) into n from pg_constraint c
   where c.conrelid = 'public.transferencias'::regclass and c.contype = 'f' and c.confrelid = 'public.cuentas'::regclass
     and c.confdeltype = 'a' and array_length(c.conkey, 1) = 2
     and (select string_agg(a.attname, ',' order by k.ord) from unnest(c.conkey) with ordinality k(attnum, ord)
            join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k.attnum) in ('cuenta_origen_id,usuario_id', 'cuenta_destino_id,usuario_id');
  if n <> 2 then raise exception 'faltan las 2 llaves compuestas (cuenta, usuario_id) ON DELETE NO ACTION (hay %)', n; end if;
  select count(*) into n from pg_constraint where conrelid = 'public.transferencias'::regclass and contype = 'f' and confdeltype = 'c'
     and confrelid = 'public.users'::regclass;
  if n <> 1 then raise exception 'transferencias.usuario_id debe ser ON DELETE CASCADE'; end if;
  select count(*) into n from pg_constraint where conrelid = 'public.transferencias'::regclass and contype = 'c';
  if n <> 2 then raise exception 'se esperaban 2 CHECK (origen<>destino y monto), hay %', n; end if;
  -- índices por origen y destino (con INCLUDE para no leer la tabla)
  select count(*) into n from pg_indexes where schemaname = 'public' and tablename = 'transferencias'
     and ((indexname = 'idx_transferencias_origen' and indexdef like '%(cuenta_origen_id) INCLUDE (monto, usuario_id)%')
       or (indexname = 'idx_transferencias_destino' and indexdef like '%(cuenta_destino_id) INCLUDE (monto, usuario_id)%'));
  if n <> 2 then raise exception 'faltan los índices por origen y destino con INCLUDE (monto, usuario_id)'; end if;
  raise notice 'OK: INV-021/046/049 RLS sin políticas, permisos, columnas, llaves compuestas NO ACTION, CHECK e índices';

  -- test_inv048_fz001_saldo_transferencias_es_before: tgtype 1 = fila, 2 = BEFORE, 4 = INSERT, 8 = DELETE, 16 = UPDATE
  select t.tgname, t.tgrelid::regclass::text as tabla, t.tgtype into r
    from pg_trigger t where not t.tgisinternal and t.tgname = 'fz001_saldo_transferencias';
  if r.tgname is null then raise exception 'falta el disparador fz001_saldo_transferencias'; end if;
  if r.tgtype & 3 <> 3 then raise exception 'fz001_saldo_transferencias debe ser BEFORE ... FOR EACH ROW (tgtype %)', r.tgtype; end if;
  if r.tabla <> 'transferencias' or r.tgtype & 28 <> 12 then
    raise exception 'fz001_saldo_transferencias debe ser solo INSERT y DELETE sobre transferencias (% %)', r.tabla, r.tgtype;
  end if;
  select count(*) into n from pg_trigger where tgrelid = 'public.transferencias'::regclass and not tgisinternal;
  if n <> 1 then raise exception 'transferencias debe tener solo el disparador fz001_ (hay %)', n; end if;
  select count(*) into n from pg_trigger where tgrelid = 'public.transferencias'::regclass and not tgisinternal
     and tgtype & 2 = 2 and tgname collate "C" < 'fz001_saldo_transferencias';
  if n <> 0 then raise exception 'hay un disparador BEFORE que se ejecutaría antes que fz001_saldo_transferencias'; end if;
  raise notice 'OK: INV-048 fz001_saldo_transferencias es BEFORE INSERT OR DELETE por fila sobre transferencias';
end $$;

-- 2. Saldo con transferencias, FZ001, tarjeta de crédito, tope, propiedad (INV-046 a INV-049, INV-051)
do $$
declare u1 uuid := '00000000-0000-4000-8000-000000002411'; u2 uuid := '00000000-0000-4000-8000-000000002412';
  a uuid := '00000000-0000-4000-8000-0000000024b1'; b uuid := '00000000-0000-4000-8000-0000000024b2';
  tj uuid := '00000000-0000-4000-8000-0000000024b3'; cx uuid := '00000000-0000-4000-8000-0000000024b4';
  t1 uuid; t2 uuid; t3 uuid; s numeric; n bigint;
begin
  insert into users(id, email) values (u1, 'trf_1@x.test'), (u2, 'trf_2@x.test');
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values
    (a, u1, 'Efectivo', 'efectivo', 1000), (b, u1, 'Ahorros', 'ahorros_corriente', 0),
    (tj, u1, 'Visa', 'tarjeta_credito', 0), (cx, u2, 'Ajena', 'efectivo', 5000);
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u1, 200, current_date, 'ingreso', a);

  -- INV-047/049: la transferencia suma al destino y resta al origen; la fecha futura ya cuenta; no son transacciones
  select count(*) into n from transacciones where usuario_id = u1;
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha, descripcion) values (u1, a, b, 300, current_date, 'ahorro') returning id into t1;
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (u1, a, b, 100.50, current_date + 400) returning id into t2;
  if cuenta_saldo_actual(a) <> 799.50 or cuenta_saldo_actual(b) <> 400.50 then
    raise exception 'saldos tras transferir: % / % (esperado 799.50 / 400.50)', cuenta_saldo_actual(a), cuenta_saldo_actual(b);
  end if;
  select saldo into s from cuentas_con_saldo(u1) where id = a;
  if s <> 799.50 then raise exception 'cuentas_con_saldo(a) = % (esperado 799.50)', s; end if;
  select saldo into s from cuentas_con_saldo(u1) where id = b;
  if s <> 400.50 then raise exception 'cuentas_con_saldo(b) = % (esperado 400.50)', s; end if;
  if (select sum(saldo) from cuentas_con_saldo(u1)) <> 1200 then raise exception 'la suma de saldos debe seguir siendo 1200 (1000 + 200)'; end if;
  if (select count(*) from transacciones where usuario_id = u1) <> n then raise exception 'una transferencia no debe crear transacciones'; end if;
  raise notice 'OK: INV-047/049 transferir resta al origen y suma al destino (fecha futura incluida) sin crear transacciones; la suma no cambia';

  -- INV-048: dejar el origen exactamente en 0 pasa; un centavo más, FZ001 y no se guarda nada
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (u1, a, b, 799.50, current_date) returning id into t3;
  if cuenta_saldo_actual(a) <> 0 then raise exception 'el origen debía quedar en 0'; end if;
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (%L, %L, %L, 0.01, current_date)$q$, u1, a, b), 'FZ001', 'transferir 0,01 con origen en 0');
  if (select count(*) from transferencias where usuario_id = u1) <> 3 or cuenta_saldo_actual(a) <> 0 then raise exception 'la transferencia rechazada dejó rastro'; end if;
  -- eliminar una transferencia devuelve el saldo al origen; si deja el destino en negativo, FZ001
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u1, 1200, current_date, 'gasto', b);   -- el destino b (1200) queda en 0
  perform pg_temp.debe_fallar(format('delete from transferencias where id = %L', t1), 'FZ001', 'eliminar una transferencia con el destino ya gastado');
  perform pg_temp.debe_fallar(format('delete from transferencias where id = %L', t3), 'FZ001', 'eliminar con el destino ya gastado (otra)');
  perform pg_temp.debe_fallar(format('delete from transferencias where id = %L', t2), 'FZ001', 'eliminar con el destino ya gastado (fecha futura)');
  if cuenta_saldo_actual(b) <> 0 then raise exception 'los rechazos cambiaron el saldo'; end if;
  delete from transacciones where usuario_id = u1 and cuenta_id = b and tipo = 'gasto';
  delete from transferencias where id = t3;     -- el destino queda en 400.50 y el origen recupera 799.50
  if cuenta_saldo_actual(a) <> 799.50 or cuenta_saldo_actual(b) <> 400.50 then
    raise exception 'saldos tras eliminar: % / %', cuenta_saldo_actual(a), cuenta_saldo_actual(b);
  end if;
  raise notice 'OK: INV-048/049 FZ001 al transferir de más y al eliminar una transferencia que dejaría el destino negativo; eliminar revierte';

  -- Tarjeta de crédito: puede quedar negativa al sacar (adelanto) y recibir no la afecta
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (u1, tj, b, 500, current_date) returning id into t1;
  if cuenta_saldo_actual(tj) <> -500 or cuenta_saldo_actual(b) <> 900.50 then raise exception 'adelanto de tarjeta: % / %', cuenta_saldo_actual(tj), cuenta_saldo_actual(b); end if;
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (u1, b, tj, 100, current_date);   -- pagar la tarjeta
  if cuenta_saldo_actual(tj) <> -400 then raise exception 'pagar la tarjeta debe subir su saldo a −400'; end if;
  -- eliminar el pago de la tarjeta (el destino es una tarjeta: nunca FZ001 por ella)
  delete from transferencias where usuario_id = u1 and cuenta_origen_id = b and cuenta_destino_id = tj;
  -- eliminar el adelanto deja el destino b (900.50 → 400.50) sin negativo: sí; la tarjeta vuelve a 0
  delete from transferencias where id = t1;
  if cuenta_saldo_actual(tj) <> 0 then raise exception 'la tarjeta debía volver a 0'; end if;
  raise notice 'OK: INV-048 la tarjeta de crédito puede quedar negativa al transferir desde ella y no bloquea pagos';

  -- CHECK: mismo origen y destino, monto 0, negativo, sobre el tope, descripción larga
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (%L, %L, %L, 1, current_date)$q$, u1, a, a), '23514', 'origen igual al destino');
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (%L, %L, %L, 0, current_date)$q$, u1, a, b), '23514', 'monto 0');
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (%L, %L, %L, -5, current_date)$q$, u1, a, b), '23514', 'monto negativo');
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (%L, %L, %L, 10000000000, current_date)$q$, u1, tj, b), '22003', 'monto 10 000 000 000');
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha, descripcion) values (%L, %L, %L, 1, current_date, %L)$q$, u1, a, b, repeat('x', 256)), '22001', 'descripción de 256');
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha, descripcion) values (u1, tj, b, 9999999999.99, current_date, repeat('x', 255)) returning id into t1;
  delete from transferencias where id = t1;   -- el destino b tenía 400.50 + 9 999 999 999,99: bajar queda en 400.50
  raise notice 'OK: INV-049/051 CHECK origen<>destino y monto (0, negativo, tope 9 999 999 999,99), descripción ≤ 255';

  -- INV-046: la BD rechaza cuentas de otro usuario (origen, destino, usuario nulo)
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (%L, %L, %L, 1, current_date)$q$, u1, a, cx), '23503', 'destino ajeno');
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (%L, %L, %L, 1, current_date)$q$, u1, cx, b), '23503', 'origen ajeno');
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (%L, %L, %L, 1, current_date)$q$, u2, a, b), '23503', 'cuentas de otro usuario como propias');
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (null, %L, %L, 1, current_date)$q$, a, b), '23502', 'usuario nulo');
  raise notice 'OK: INV-046 la llave compuesta rechaza cuentas de otro usuario en origen y destino';
end $$;

-- 3. Archivada = congelada, FZ002 antes que FZ001, al crear y al eliminar (INV-050)
do $$
declare u1 uuid := '00000000-0000-4000-8000-000000002411';
  a uuid := '00000000-0000-4000-8000-0000000024b1'; b uuid := '00000000-0000-4000-8000-0000000024b2';
  ca uuid := '00000000-0000-4000-8000-0000000024c1'; cb uuid := '00000000-0000-4000-8000-0000000024c2'; t1 uuid;
begin
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values (ca, u1, 'Congelable', 'efectivo', 10), (cb, u1, 'Libre', 'efectivo', 10);
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (u1, cb, ca, 5, current_date) returning id into t1;
  update cuentas set archivada = true where id = ca;
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (%L, %L, %L, 1, current_date)$q$, u1, cb, ca), 'FZ002', 'transferir a archivada');
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (%L, %L, %L, 1, current_date)$q$, u1, ca, cb), 'FZ002', 'transferir desde archivada');
  perform pg_temp.debe_fallar(format($q$insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (%L, %L, %L, 1000000, current_date)$q$, u1, ca, cb), 'FZ002', 'sin saldo desde archivada (FZ002 antes que FZ001)');
  perform pg_temp.debe_fallar(format('delete from transferencias where id = %L', t1), 'FZ002', 'eliminar con el destino archivado');
  -- también si es el origen el archivado
  update cuentas set archivada = false where id = ca;
  delete from transferencias where id = t1;
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (u1, ca, cb, 5, current_date) returning id into t1;
  update cuentas set archivada = true where id = ca;
  perform pg_temp.debe_fallar(format('delete from transferencias where id = %L', t1), 'FZ002', 'eliminar con el origen archivado');
  if (select saldo from cuentas_con_saldo(u1) where id = ca) <> 5 then raise exception 'el saldo de la archivada debe seguir consultándose (5)'; end if;
  update cuentas set archivada = false where id = ca;
  delete from transferencias where id = t1;
  raise notice 'OK: INV-050 archivada = congelada al crear y eliminar transferencias (FZ002 antes que FZ001); desarchivar permite operar';
end $$;

-- 4. Eliminar una cuenta con transferencias (origen o destino) no se puede (NO ACTION → 23503); sin ellas, sí (INV-050)
do $$
declare u1 uuid := '00000000-0000-4000-8000-000000002411';
  d1 uuid := '00000000-0000-4000-8000-0000000024d1'; d2 uuid := '00000000-0000-4000-8000-0000000024d2'; d3 uuid := '00000000-0000-4000-8000-0000000024d3';
begin
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values (d1, u1, 'D1', 'efectivo', 10), (d2, u1, 'D2', 'efectivo', 0), (d3, u1, 'D3', 'efectivo', 0);
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (u1, d1, d2, 4, current_date);
  perform pg_temp.debe_fallar(format('delete from cuentas where id = %L', d1), '23503', 'eliminar cuenta que es origen de una transferencia');
  perform pg_temp.debe_fallar(format('delete from cuentas where id = %L', d2), '23503', 'eliminar cuenta que es destino de una transferencia');
  delete from cuentas where id = d3;
  raise notice 'OK: INV-050 una cuenta con transferencias (origen o destino) no se elimina (23503); sin ellas sí';
end $$;

-- 5. Borrar un usuario con transferencias: la cascada no lanza FZ001/FZ002 ni error de llave (INV-021, REQ-F-013)
do $$
declare u4 uuid := '00000000-0000-4000-8000-000000002414';
  e uuid := '00000000-0000-4000-8000-0000000024e1'; ar uuid := '00000000-0000-4000-8000-0000000024e2'; tj uuid := '00000000-0000-4000-8000-0000000024e3';
  n bigint;
begin
  insert into users(id, email) values (u4, 'trf_4@x.test');
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values (e, u4, 'Efectivo', 'efectivo', 100), (ar, u4, 'Vieja', 'efectivo', 0), (tj, u4, 'Tarjeta', 'tarjeta_credito', 0);
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (u4, e, ar, 100, current_date), (u4, tj, e, 50, current_date);
  update cuentas set archivada = true where id = ar;      -- cuenta archivada con transferencias que la financian
  delete from users where id = u4;
  select (select count(*) from cuentas where usuario_id = u4) + (select count(*) from transferencias where usuario_id = u4) into n;
  if n <> 0 then raise exception 'quedaron % filas del usuario borrado', n; end if;
  raise notice 'OK: INV-021/050 borrar un usuario con transferencias (cuenta archivada y tarjeta incluidas) funciona sin FZ001 ni FZ002';
end $$;

-- 6. Como service_role (el rol del backend): crea y elimina transferencias y los disparadores se ejecutan
do $$
declare u6 uuid := '00000000-0000-4000-8000-000000002416'; a uuid := '00000000-0000-4000-8000-0000000024f1'; b uuid := '00000000-0000-4000-8000-0000000024f2'; s numeric; t uuid;
begin
  if not exists (select 1 from pg_roles where rolname = 'service_role') then return; end if;
  insert into users(id, email) values (u6, 'trf_6@x.test');
  set local role service_role;
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values (a, u6, 'A', 'efectivo', 100), (b, u6, 'B', 'efectivo', 0);
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (u6, a, b, 60, current_date) returning id into t;
  begin
    insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha) values (u6, a, b, 41, current_date);
    raise exception 'debía fallar con FZ001';
  exception when sqlstate 'FZ001' then null;
  end;
  select saldo into s from cuentas_con_saldo(u6) where id = a;
  delete from transferencias where id = t;
  reset role;
  if s <> 40 then raise exception 'service_role: saldo esperado 40, fue %', s; end if;
  raise notice 'OK: service_role crea y elimina transferencias, el disparador se ejecuta y cuentas_con_saldo funciona';
end $$;

-- 7. REQ-N-022: 20 cuentas, 50 000 transacciones y 20 000 transferencias; una sola consulta agregada con índices y rápida
create function pg_temp.plan(p_sql text) returns text language plpgsql as $$
declare l text; r text := '';
begin for l in execute 'explain (costs off) ' || p_sql loop r := r || l || E'\n'; end loop; return r; end $$;
do $$
declare u5 uuid := '00000000-0000-4000-8000-000000002415'; t0 timestamptz; ms numeric; plan text; n integer;
begin
  insert into users(id, email) values (u5, 'trf_5@x.test');
  insert into cuentas(usuario_id, nombre, tipo, saldo_inicial) select u5, 'Cuenta ' || g, 'efectivo', 0 from generate_series(1, 20) g;
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id)
    select u5, 10 + (g % 7), current_date - (g % 300), 'ingreso', (select id from cuentas where usuario_id = u5 and nombre = 'Cuenta ' || (1 + g % 20))
      from generate_series(1, 50000) g;
  insert into transferencias(usuario_id, cuenta_origen_id, cuenta_destino_id, monto, fecha)
    select u5, (select id from cuentas where usuario_id = u5 and nombre = 'Cuenta ' || (1 + g % 20)),
               (select id from cuentas where usuario_id = u5 and nombre = 'Cuenta ' || (1 + (g + 1) % 20)), 1, current_date - (g % 300)
      from generate_series(1, 20000) g;
  analyze public.transacciones; analyze public.cuentas; analyze public.transferencias;
  t0 := clock_timestamp();
  select count(*) into n from cuentas_con_saldo(u5);
  ms := extract(epoch from clock_timestamp() - t0) * 1000;
  if n <> 20 then raise exception 'debían salir 20 cuentas, salieron %', n; end if;
  if ms > 1000 then raise exception 'cuentas_con_saldo tardó % ms (> 1 s)', ms; end if;
  if (select sum(saldo) from cuentas_con_saldo(u5)) <> (select sum(monto) from transacciones where usuario_id = u5) then
    raise exception 'las transferencias no deben cambiar la suma de saldos';
  end if;
  plan := pg_temp.plan(format($q$
    select c.id, c.saldo_inicial + coalesce(r.recibido, 0) - coalesce(e.enviado, 0) from public.cuentas c
      left join lateral (select sum(x.monto) as recibido from public.transferencias x where x.cuenta_destino_id = c.id and x.usuario_id = c.usuario_id) r on true
      left join lateral (select sum(x.monto) as enviado from public.transferencias x where x.cuenta_origen_id = c.id and x.usuario_id = c.usuario_id) e on true
     where c.usuario_id = %L$q$, u5));
  if plan not like '%idx_transferencias_origen%' or plan not like '%idx_transferencias_destino%' then
    raise exception 'el saldo no usa los índices por origen y destino: %', plan;
  end if;
  raise notice 'OK: REQ-N-022 cuentas_con_saldo con 20 cuentas, 50 000 transacciones y 20 000 transferencias tardó % ms y usa los índices', round(ms);
end $$;

-- Limpieza: los usuarios de prueba (la cascada borra sus cuentas, transacciones y transferencias)
do $$ declare n bigint; begin
  delete from users where email like 'trf\_%@x.test';
  select (select count(*) from cuentas) + (select count(*) from transferencias) into n;
  if n <> 0 then raise exception 'quedaron % filas tras borrar los usuarios de prueba', n; end if;
  raise notice 'OK: limpieza (cascada de usuarios con transferencias)';
end $$;
