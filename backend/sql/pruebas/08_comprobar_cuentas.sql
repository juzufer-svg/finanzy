-- CHG-019 fase (a) · INV-046 a INV-051: cuentas de dinero (después de 2026-11-25_cuentas.sql, ejecutado dos veces)
-- La concurrencia real (sesiones simultáneas) está en probar.sh. Se ejecuta desde backend/sql/pruebas (usa \ir con ruta relativa).
-- Los usuarios de prueba tienen correo «cta_...@x.test» y se borran al final.

-- 0. La migración no toca los datos existentes y se puede repetir (REQ-N-025): mismas filas, todas con cuenta_id nulo
select count(*) as n_antes from public.transacciones \gset
do $$ declare n bigint; begin
  select count(*) into n from public.transacciones where cuenta_id is not null;
  if n <> 0 then raise exception 'las transacciones existentes deben quedar sin cuenta (hay % con cuenta)', n; end if;
end $$;
\ir ../2026-11-25_cuentas.sql
select count(*) as n_despues from public.transacciones \gset
select (:n_antes <> :n_despues) as cambio \gset
\if :cambio
  \echo ERROR: la migración cambió el número de transacciones (:n_antes -> :n_despues)
  select 1 / 0;
\endif
\echo OK: la migración se repite sin tocar las :n_antes filas existentes (todas sin cuenta)

-- 1. RLS, privilegios, columnas, llaves, disparadores BEFORE (INV-021, INV-046, INV-048)
do $$
declare n bigint; f text; cols text; r record;
  funciones text[] := array['public.cuenta_saldo_actual(uuid)', 'public.cuentas_con_saldo(uuid)',
    'public.fz001_saldo_transacciones_fn()', 'public.fz001_saldo_cuentas_fn()', 'public.fz003_tope_cuentas_fn()'];
begin
  select count(*) into n from pg_tables where schemaname = 'public' and tablename = 'cuentas' and rowsecurity;
  if n <> 1 then raise exception 'cuentas sin RLS'; end if;
  select count(*) into n from pg_policies where schemaname = 'public' and tablename = 'cuentas';
  if n <> 0 then raise exception 'cuentas no debe tener políticas (hay %)', n; end if;
  if has_table_privilege('anon', 'public.cuentas', 'select') or has_table_privilege('authenticated', 'public.cuentas', 'select')
     or has_table_privilege('anon', 'public.cuentas', 'insert,update,delete')
     or has_table_privilege('authenticated', 'public.cuentas', 'insert,update,delete') then
    raise exception 'anon/authenticated tienen acceso a cuentas';
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role')
     and not has_table_privilege('service_role', 'public.cuentas', 'select,insert,update,delete') then
    raise exception 'service_role no tiene acceso a cuentas';
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
  -- cuentas_con_saldo es STABLE y devuelve SOLO las columnas de la lista blanca; el saldo vigente es VOLATILE (ve lo confirmado tras esperar)
  select count(*) into n from pg_proc where oid = to_regprocedure('public.cuentas_con_saldo(uuid)') and provolatile = 's';
  if n <> 1 then raise exception 'cuentas_con_saldo debe ser STABLE'; end if;
  select count(*) into n from pg_proc where oid = to_regprocedure('public.cuenta_saldo_actual(uuid)') and provolatile = 'v';
  if n <> 1 then raise exception 'cuenta_saldo_actual debe ser VOLATILE'; end if;
  select array_to_string(proargnames, ',') into cols from pg_proc where oid = to_regprocedure('public.cuentas_con_saldo(uuid)');
  if cols <> 'p_usuario_id,id,usuario_id,nombre,tipo,saldo_inicial,archivada,created_at,saldo' then
    raise exception 'columnas de cuentas_con_saldo fuera de la lista blanca: %', cols;
  end if;
  -- test_inv047_no_existe_columna_de_saldo_guardado
  select string_agg(column_name, ',' order by column_name) into cols
    from information_schema.columns where table_schema = 'public' and table_name = 'cuentas';
  if cols <> 'archivada,created_at,id,nombre,saldo_inicial,tipo,usuario_id' then raise exception 'columnas de cuentas: %', cols; end if;
  select count(*) into n from information_schema.columns
   where table_schema = 'public' and table_name = 'transacciones' and column_name = 'cuenta_id' and is_nullable = 'YES' and data_type = 'uuid';
  if n <> 1 then raise exception 'transacciones.cuenta_id debe ser uuid nulo'; end if;
  -- llave foránea compuesta (cuenta_id, usuario_id) con NO ACTION (no RESTRICT: ADR-009 punto 2)
  select count(*) into n from pg_constraint c
   where c.conrelid = 'public.transacciones'::regclass and c.contype = 'f' and c.confrelid = 'public.cuentas'::regclass
     and c.confdeltype = 'a' and array_length(c.conkey, 1) = 2
     and (select string_agg(a.attname, ',' order by k.ord) from unnest(c.conkey) with ordinality k(attnum, ord)
            join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k.attnum) = 'cuenta_id,usuario_id';
  if n <> 1 then raise exception 'falta la llave compuesta (cuenta_id, usuario_id) ON DELETE NO ACTION'; end if;
  select count(*) into n from pg_constraint where conrelid = 'public.cuentas'::regclass and contype = 'f' and confdeltype = 'c';
  if n <> 1 then raise exception 'cuentas.usuario_id debe ser ON DELETE CASCADE'; end if;
  select count(*) into n from pg_indexes where schemaname = 'public' and indexname in ('idx_transacciones_cuenta', 'idx_cuentas_usuario_nombre');
  if n <> 2 then raise exception 'faltan índices de cuentas'; end if;
  raise notice 'OK: INV-021/046/047 RLS sin políticas, permisos, lista blanca, sin columna de saldo y llave compuesta NO ACTION';

  -- test_inv048_los_disparadores_fz001_son_before: tgtype 1 = fila, 2 = BEFORE, 4 = INSERT, 8 = DELETE, 16 = UPDATE
  for r in select t.tgname, t.tgrelid::regclass::text as tabla, t.tgtype,
                  (select string_agg(a.attname, ',' order by a.attname) from unnest(t.tgattr::int2[]) k(n)
                     join pg_attribute a on a.attrelid = t.tgrelid and a.attnum = k.n) as columnas
             from pg_trigger t where not t.tgisinternal and t.tgname in ('fz001_saldo_transacciones', 'fz001_saldo_cuentas', 'fz003_tope_cuentas') loop
    if r.tgtype & 3 <> 3 then raise exception '% debe ser BEFORE ... FOR EACH ROW (tgtype %)', r.tgname, r.tgtype; end if;
    if r.tgname = 'fz001_saldo_transacciones' and not (r.tabla = 'transacciones' and r.tgtype & 28 = 28 and r.columnas = 'cuenta_id,monto,tipo') then
      raise exception 'fz001_saldo_transacciones mal definido (% % %)', r.tabla, r.tgtype, r.columnas;
    end if;
    if r.tgname = 'fz001_saldo_cuentas' and not (r.tabla = 'cuentas' and r.tgtype & 28 = 16 and r.columnas = 'saldo_inicial') then
      raise exception 'fz001_saldo_cuentas mal definido (% % %)', r.tabla, r.tgtype, r.columnas;
    end if;
    if r.tgname = 'fz003_tope_cuentas' and not (r.tabla = 'cuentas' and r.tgtype & 28 = 4) then
      raise exception 'fz003_tope_cuentas mal definido (% %)', r.tabla, r.tgtype;
    end if;
  end loop;
  select count(*) into n from pg_trigger where not tgisinternal and tgname in ('fz001_saldo_transacciones', 'fz001_saldo_cuentas', 'fz003_tope_cuentas');
  if n <> 3 then raise exception 'se esperaban 3 disparadores fz001_/fz003_, hay %', n; end if;
  -- ningún otro disparador BEFORE de transacciones puede ejecutarse antes (el orden es por nombre)
  select count(*) into n from pg_trigger where tgrelid = 'public.transacciones'::regclass and not tgisinternal
     and tgtype & 2 = 2 and tgname collate "C" < 'fz001_saldo_transacciones';
  if n <> 0 then raise exception 'hay un disparador BEFORE que se ejecutaría antes que fz001_saldo_transacciones'; end if;
  raise notice 'OK: INV-048 los tres disparadores fz001_/fz003_ son BEFORE por fila y se llaman como la spec';
end $$;

-- Auxiliar: la sentencia debe fallar con ese SQLSTATE y NO dejar nada (la subtransacción se revierte)
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


-- 2. Saldo derivado, FZ001, tarjeta de crédito, tope de monto y propiedad (INV-046, INV-047, INV-048, INV-051)
do $$
declare u1 uuid := '00000000-0000-4000-8000-000000001901'; u2 uuid := '00000000-0000-4000-8000-000000001902';
  c1 uuid := '00000000-0000-4000-8000-0000000019c1'; c2 uuid := '00000000-0000-4000-8000-0000000019c2';
  tj uuid := '00000000-0000-4000-8000-0000000019c3'; cx uuid := '00000000-0000-4000-8000-0000000019c4';
  t1 uuid; t2 uuid; s numeric;
begin
  insert into users(id, email) values (u1, 'cta_1@x.test'), (u2, 'cta_2@x.test');
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values
    (c1, u1, 'Efectivo', 'efectivo', 1000), (c2, u1, 'Ahorros', 'ahorros_corriente', 0),
    (tj, u1, 'Visa', 'tarjeta_credito', 0), (cx, u2, 'Ajena', 'efectivo', 5000);

  -- INV-047: saldo = saldo_inicial + ingresos − gastos; la fecha futura ya cuenta; sin cuenta no mueve nada
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u1, 300, current_date, 'ingreso', c1);
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u1, 200, current_date + 400, 'gasto', c1);
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u1, 999, current_date, 'gasto', null);
  select saldo into s from cuentas_con_saldo(u1) where id = c1;
  if s <> 1100 then raise exception 'saldo esperado 1100 (1000 + 300 − 200 con la fecha futura), fue %', s; end if;
  if cuenta_saldo_actual(c1) <> 1100 then raise exception 'cuenta_saldo_actual difiere de cuentas_con_saldo'; end if;
  select saldo into s from cuentas_con_saldo(u1) where id = c2;
  if s <> 0 then raise exception 'la cuenta sin transacciones debe tener su saldo inicial'; end if;
  if exists (select 1 from cuentas_con_saldo(u1) where id = cx) then raise exception 'cuentas_con_saldo mostró una cuenta de otro usuario'; end if;
  if (select count(*) from cuentas_con_saldo(u1)) <> 3 then raise exception 'u1 debe ver exactamente sus 3 cuentas'; end if;
  raise notice 'OK: INV-047 saldo = inicial + ingresos − gastos, incluye fechas futuras; sin cuenta no mueve; no mezcla usuarios';

  -- INV-048: el gasto que deja saldo exactamente 0 pasa; un centavo más, FZ001 y no se guarda nada
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u1, 1100, current_date, 'gasto', c1);
  perform pg_temp.debe_fallar(format($q$insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (%L, 0.01, current_date, 'gasto', %L)$q$, u1, c1), 'FZ001', 'gasto de 0,01 con saldo 0');
  if cuenta_saldo_actual(c1) <> 0 then raise exception 'el gasto rechazado cambió el saldo'; end if;
  select id into t1 from transacciones where cuenta_id = c1 and tipo = 'gasto' and monto = 1100;
  select id into t2 from transacciones where cuenta_id = c1 and tipo = 'ingreso';
  perform pg_temp.debe_fallar(format('update transacciones set monto = 1100.01 where id = %L', t1), 'FZ001', 'editar el monto de un gasto');
  perform pg_temp.debe_fallar(format('delete from transacciones where id = %L', t2), 'FZ001', 'eliminar el ingreso que financia un gasto');
  perform pg_temp.debe_fallar(format('update transacciones set monto = 299 where id = %L', t2), 'FZ001', 'bajar el monto de un ingreso');
  perform pg_temp.debe_fallar(format('update transacciones set tipo = ''gasto'' where id = %L', t2), 'FZ001', 'cambiar un ingreso a gasto');
  perform pg_temp.debe_fallar(format('update transacciones set cuenta_id = %L where id = %L', c2, t2), 'FZ001', 'mover el ingreso que financia a otra cuenta');
  perform pg_temp.debe_fallar(format('update cuentas set saldo_inicial = 999.99 where id = %L', c1), 'FZ001', 'bajar saldo_inicial');
  if cuenta_saldo_actual(c1) <> 0 then raise exception 'los rechazos cambiaron el saldo'; end if;
  update cuentas set saldo_inicial = 1500 where id = c1;                         -- subir siempre se puede (saldo 500)
  update transacciones set monto = 1100.01 where id = t1;                         -- con saldo 500 sí alcanza
  update transacciones set monto = 1100 where id = t1;
  update transacciones set monto = monto, tipo = tipo, cuenta_id = cuenta_id where id = t2;   -- reenviar los mismos valores
  update cuentas set saldo_inicial = 1000 where id = c1;                         -- bajar hasta dejar saldo 0 sí se puede
  -- mover un gasto entre cuentas con saldo suficiente
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u1, 5000, current_date, 'ingreso', c2);
  update transacciones set cuenta_id = c2 where id = t1;
  if cuenta_saldo_actual(c1) <> 1100 or cuenta_saldo_actual(c2) <> 3900 then raise exception 'saldos tras mover el gasto: % / %', cuenta_saldo_actual(c1), cuenta_saldo_actual(c2); end if;
  update transacciones set cuenta_id = c1 where id = t1;
  -- eliminar un gasto devuelve el saldo
  delete from transacciones where id = t1;
  if cuenta_saldo_actual(c1) <> 1100 then raise exception 'eliminar un gasto debe devolver su saldo'; end if;
  raise notice 'OK: INV-048 FZ001 en gasto, edición, baja, cambio de tipo, cambio de cuenta y bajada del saldo inicial; el rechazo no guarda nada';

  -- Tarjeta de crédito: sí puede quedar negativa (y con deuda inicial)
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u1, 500, current_date, 'gasto', tj);
  if cuenta_saldo_actual(tj) <> -500 then raise exception 'la tarjeta debe poder quedar en −500'; end if;
  update cuentas set saldo_inicial = -200 where id = tj;
  if cuenta_saldo_actual(tj) <> -700 then raise exception 'la tarjeta con deuda inicial −200 debe quedar en −700'; end if;
  perform pg_temp.debe_fallar(format($q$insert into cuentas(usuario_id, nombre, tipo, saldo_inicial) values (%L, 'Negativa', 'efectivo', -1)$q$, u1), '23514', 'saldo_inicial negativo en efectivo');
  raise notice 'OK: INV-048 la tarjeta de crédito puede quedar negativa; efectivo con saldo inicial negativo se rechaza';

  -- INV-051: tope de NUMERIC(12,2) en el saldo inicial y en las transacciones con cuenta
  insert into cuentas(usuario_id, nombre, tipo, saldo_inicial) values (u1, 'Tope', 'ahorros_corriente', 9999999999.99);
  perform pg_temp.debe_fallar(format($q$insert into cuentas(usuario_id, nombre, tipo, saldo_inicial) values (%L, 'Sobre el tope', 'ahorros_corriente', 10000000000)$q$, u1), '22003', 'saldo inicial 10 000 000 000');
  perform pg_temp.debe_fallar(format($q$insert into cuentas(usuario_id, nombre, tipo, saldo_inicial) values (%L, 'Deuda enorme', 'tarjeta_credito', -10000000000)$q$, u1), '22003', 'deuda inicial de 10 000 000 000');
  insert into cuentas(usuario_id, nombre, tipo, saldo_inicial) values (u1, 'Deuda tope', 'tarjeta_credito', -9999999999.99);
  perform pg_temp.debe_fallar(format($q$insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (%L, 10000000000, current_date, 'ingreso', %L)$q$, u1, c1), '22003', 'ingreso sobre el tope con cuenta');
  raise notice 'OK: INV-051 9 999 999 999,99 se acepta y 10 000 000 000 se rechaza (saldo inicial y transacciones)';

  -- INV-046: la BD rechaza la cuenta de otro usuario al crear y al editar (llave compuesta)
  perform pg_temp.debe_fallar(format($q$insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (%L, 1, current_date, 'ingreso', %L)$q$, u1, cx), '23503', 'transacción con cuenta ajena');
  perform pg_temp.debe_fallar(format('update transacciones set cuenta_id = %L where id = %L', cx, t2), '23503', 'editar con cuenta ajena');
  perform pg_temp.debe_fallar(format($q$insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (null, 1, current_date, 'ingreso', %L)$q$, c1), '23514', 'cuenta sin usuario');
  if (select count(*) from transacciones where cuenta_id = cx) <> 0 then raise exception 'quedó una transacción en la cuenta ajena'; end if;
  raise notice 'OK: INV-046 la llave compuesta rechaza la cuenta de otro usuario al crear y al editar';
end $$;

-- 3. Archivada = congelada, FZ002 antes que FZ001 (INV-050)
do $$
declare u1 uuid := '00000000-0000-4000-8000-000000001901'; u2 uuid := '00000000-0000-4000-8000-000000001902';
  ca uuid := '00000000-0000-4000-8000-0000000019a1'; cb uuid := '00000000-0000-4000-8000-0000000019a2'; t1 uuid;
begin
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values (ca, u1, 'Congelable', 'efectivo', 100), (cb, u1, 'Libre', 'efectivo', 100);
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u1, 10, current_date, 'ingreso', ca) returning id into t1;
  update cuentas set archivada = true where id = ca;     -- archivar con saldo distinto de 0 y con transacciones se puede
  perform pg_temp.debe_fallar(format($q$insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (%L, 1, current_date, 'ingreso', %L)$q$, u1, ca), 'FZ002', 'insertar en archivada');
  perform pg_temp.debe_fallar(format($q$insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (%L, 1000000, current_date, 'gasto', %L)$q$, u1, ca), 'FZ002', 'gasto sin saldo en archivada (FZ002 antes que FZ001)');
  perform pg_temp.debe_fallar(format('update transacciones set monto = 11 where id = %L', t1), 'FZ002', 'cambiar el monto en archivada');
  perform pg_temp.debe_fallar(format('update transacciones set tipo = ''ingreso'' , monto = 12 where id = %L', t1), 'FZ002', 'cambiar monto y tipo en archivada');
  perform pg_temp.debe_fallar(format('delete from transacciones where id = %L', t1), 'FZ002', 'eliminar de archivada');
  perform pg_temp.debe_fallar(format('update transacciones set cuenta_id = %L where id = %L', cb, t1), 'FZ002', 'sacar de archivada');
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u1, 1, current_date, 'ingreso', cb) returning id into t1;
  perform pg_temp.debe_fallar(format('update transacciones set cuenta_id = %L where id = %L', ca, t1), 'FZ002', 'mover a archivada');
  update transacciones set monto = monto where id = t1;   -- reenviar el mismo valor no cambia nada
  -- el saldo de una archivada sigue consultándose; desarchivar permite operar de nuevo
  if (select saldo from cuentas_con_saldo(u1) where id = ca) <> 110 then raise exception 'el saldo de la archivada debe seguir siendo 110'; end if;
  update cuentas set archivada = false where id = ca;
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u1, 1, current_date, 'ingreso', ca);
  raise notice 'OK: INV-050 archivada = congelada (alta, monto, tipo, baja, cambio de cuenta → FZ002 antes que FZ001); desarchivar permite operar';
end $$;

-- 4. Nombre único sin mayúsculas ni espacios, forma del nombre y tipo, tope de 20 cuentas (INV-050, INV-051)
do $$
declare u3 uuid := '00000000-0000-4000-8000-000000001903'; u2 uuid := '00000000-0000-4000-8000-000000001902'; i integer;
begin
  insert into users(id, email) values (u3, 'cta_3@x.test');
  insert into cuentas(usuario_id, nombre, tipo) values (u3, 'Caja', 'efectivo');
  perform pg_temp.debe_fallar(format($q$insert into cuentas(usuario_id, nombre, tipo) values (%L, 'CAJA', 'efectivo')$q$, u3), '23505', 'nombre en mayúsculas');
  perform pg_temp.debe_fallar(format($q$insert into cuentas(usuario_id, nombre, tipo) values (%L, '  caja ', 'efectivo')$q$, u3), '23505', 'nombre con espacios');
  insert into cuentas(usuario_id, nombre, tipo) values (u2, 'Caja', 'efectivo');   -- otro usuario: sí
  perform pg_temp.debe_fallar(format($q$insert into cuentas(usuario_id, nombre, tipo) values (%L, '   ', 'efectivo')$q$, u3), '23514', 'nombre vacío');
  perform pg_temp.debe_fallar(format($q$insert into cuentas(usuario_id, nombre, tipo) values (%L, %L, 'efectivo')$q$, u3, repeat('x', 101)), '22001', 'nombre de 101 caracteres');
  insert into cuentas(usuario_id, nombre, tipo) values (u3, repeat('y', 100), 'billetera_digital');
  perform pg_temp.debe_fallar(format($q$insert into cuentas(usuario_id, nombre, tipo) values (%L, 'Mala', 'cripto')$q$, u3), '23514', 'tipo inválido');
  raise notice 'OK: INV-050 nombre único sin mayúsculas ni espacios; nombre 1-100; tipo de lista cerrada';
  -- tope: ya tiene 2; 18 más = 20; la 21.ª → FZ003; otro usuario no se ve afectado
  for i in 1..18 loop insert into cuentas(usuario_id, nombre, tipo) values (u3, 'C' || i, 'efectivo'); end loop;
  perform pg_temp.debe_fallar(format($q$insert into cuentas(usuario_id, nombre, tipo) values (%L, 'La 21', 'efectivo')$q$, u3), 'FZ003', 'cuenta 21');
  if (select count(*) from cuentas where usuario_id = u3) <> 20 then raise exception 'debían quedar 20 cuentas'; end if;
  insert into cuentas(usuario_id, nombre, tipo) values (u2, 'Otra', 'efectivo');
  -- archivar no libera el cupo (cuentan archivadas y no archivadas)
  update cuentas set archivada = true where usuario_id = u3 and nombre = 'C1';
  perform pg_temp.debe_fallar(format($q$insert into cuentas(usuario_id, nombre, tipo) values (%L, 'La 21 bis', 'efectivo')$q$, u3), 'FZ003', 'cuenta 21 con una archivada');
  raise notice 'OK: INV-050 tope de 20 cuentas por usuario (FZ003), contando archivadas';
end $$;

-- 5. Eliminar una cuenta, borrar un usuario con cuentas y transacciones (INV-021, INV-050)
do $$
declare u4 uuid := '00000000-0000-4000-8000-000000001904'; e uuid := '00000000-0000-4000-8000-0000000019e1';
  ar uuid := '00000000-0000-4000-8000-0000000019e2'; tj uuid := '00000000-0000-4000-8000-0000000019e3'; vacia uuid := '00000000-0000-4000-8000-0000000019e4';
  n bigint;
begin
  insert into users(id, email) values (u4, 'cta_4@x.test');
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values
    (e, u4, 'Efectivo', 'efectivo', 0), (ar, u4, 'Vieja', 'efectivo', 50), (tj, u4, 'Tarjeta', 'tarjeta_credito', 0), (vacia, u4, 'Vacía', 'efectivo', 0);
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values
    (u4, 1000, current_date, 'ingreso', e), (u4, 500, current_date, 'gasto', e), (u4, 70, current_date, 'gasto', tj), (u4, 5, current_date, 'ingreso', ar);
  update cuentas set archivada = true where id = ar;
  -- con transacciones no se puede eliminar (NO ACTION → 23503); sin ellas sí
  perform pg_temp.debe_fallar(format('delete from cuentas where id = %L', e), '23503', 'eliminar cuenta con transacciones');
  delete from cuentas where id = vacia;
  -- borrar al usuario: la cascada borra transacciones y cuentas sin FZ001/FZ002 ni error de llave (la cuenta archivada y el ingreso que financia un gasto incluidos)
  delete from users where id = u4;
  select (select count(*) from cuentas where usuario_id = u4) + (select count(*) from transacciones where usuario_id = u4) into n;
  if n <> 0 then raise exception 'quedaron % filas del usuario borrado', n; end if;
  raise notice 'OK: INV-021/050 borrar un usuario con cuentas (una archivada, una tarjeta) y transacciones funciona; eliminar cuenta con transacciones → 23503';
end $$;

-- 6. Como service_role (el rol del backend): escribe, lee los saldos y los disparadores se ejecutan
do $$
declare u6 uuid := '00000000-0000-4000-8000-000000001906'; c uuid := '00000000-0000-4000-8000-0000000019f1'; s numeric;
begin
  if not exists (select 1 from pg_roles where rolname = 'service_role') then return; end if;
  insert into users(id, email) values (u6, 'cta_6@x.test');
  set local role service_role;
  insert into cuentas(id, usuario_id, nombre, tipo, saldo_inicial) values (c, u6, 'Con service_role', 'efectivo', 100);
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u6, 60, current_date, 'gasto', c);
  begin
    insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id) values (u6, 41, current_date, 'gasto', c);
    raise exception 'debía fallar con FZ001';
  exception when sqlstate 'FZ001' then null;
  end;
  select saldo into s from cuentas_con_saldo(u6);
  reset role;
  if s <> 40 then raise exception 'service_role: saldo esperado 40, fue %', s; end if;
  raise notice 'OK: service_role escribe, los disparadores se ejecutan y cuentas_con_saldo funciona';
end $$;

-- 7. REQ-N-022: 20 cuentas y 50 000 transacciones; una sola consulta agregada con índice y rápida
create function pg_temp.plan(p_sql text) returns text language plpgsql as $$
declare l text; r text := '';
begin for l in execute 'explain (costs off) ' || p_sql loop r := r || l || E'\n'; end loop; return r; end $$;
do $$
declare u5 uuid := '00000000-0000-4000-8000-000000001905'; t0 timestamptz; ms numeric; plan text; n integer;
begin
  insert into users(id, email) values (u5, 'cta_5@x.test');
  insert into cuentas(usuario_id, nombre, tipo, saldo_inicial) select u5, 'Cuenta ' || g, 'efectivo', 0 from generate_series(1, 20) g;
  insert into transacciones(usuario_id, monto, fecha, tipo, cuenta_id)
    select u5, 10 + (g % 7), current_date - (g % 300), 'ingreso', (select id from cuentas where usuario_id = u5 and nombre = 'Cuenta ' || (1 + g % 20))
      from generate_series(1, 50000) g;
  analyze public.transacciones; analyze public.cuentas;
  t0 := clock_timestamp();
  select count(*) into n from cuentas_con_saldo(u5);
  ms := extract(epoch from clock_timestamp() - t0) * 1000;
  if n <> 20 then raise exception 'debían salir 20 cuentas, salieron %', n; end if;
  if ms > 1000 then raise exception 'cuentas_con_saldo tardó % ms (> 1 s)', ms; end if;
  plan := pg_temp.plan(format($q$
    select c.id, c.saldo_inicial + coalesce(m.neto, 0) from public.cuentas c
      left join lateral (select sum(case t.tipo when 'ingreso' then t.monto when 'gasto' then -t.monto else 0 end) as neto
                           from public.transacciones t where t.cuenta_id = c.id and t.usuario_id = c.usuario_id) m on true
     where c.usuario_id = %L$q$, u5));
  if plan not like '%idx_transacciones_cuenta%' then raise exception 'el saldo no usa el índice por cuenta: %', plan; end if;
  raise notice 'OK: REQ-N-022 cuentas_con_saldo con 20 cuentas y 50 000 transacciones tardó % ms y usa idx_transacciones_cuenta', round(ms);
end $$;

-- Limpieza: los usuarios de prueba (la cascada borra sus cuentas y transacciones)
do $$ declare n bigint; begin
  delete from users where email like 'cta\_%@x.test';
  select count(*) into n from cuentas;
  if n <> 0 then raise exception 'quedaron % cuentas tras borrar los usuarios de prueba', n; end if;
  raise notice 'OK: limpieza (cascada de usuarios con cuentas y 50 000 transacciones)';
end $$;
