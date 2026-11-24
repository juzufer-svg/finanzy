-- CHG-017 · INV-036: contadores diarios (después de 2026-11-24_monitor.sql, ejecutado dos veces)
do $$
declare n bigint; hoy date := current_date; r integer; total bigint;
begin
  -- RLS activado y sin políticas
  select count(*) into n from pg_tables where schemaname = 'public' and tablename = 'contadores_diarios' and rowsecurity;
  if n <> 1 then raise exception 'contadores_diarios sin RLS'; end if;
  select count(*) into n from pg_policies where schemaname = 'public' and tablename = 'contadores_diarios';
  if n <> 0 then raise exception 'contadores_diarios no debe tener políticas (hay %)', n; end if;
  if has_table_privilege('anon', 'public.contadores_diarios', 'select,insert,update,delete')
     or has_table_privilege('authenticated', 'public.contadores_diarios', 'select,insert,update,delete') then
    raise exception 'anon/authenticated tienen acceso a la tabla';
  end if;
  if has_function_privilege('anon', 'public.incrementar_contador(date,text,text,bigint)', 'execute')
     or has_function_privilege('authenticated', 'public.incrementar_contador(date,text,text,bigint)', 'execute')
     or has_function_privilege('anon', 'public.purgar_contadores(date)', 'execute')
     or has_function_privilege('authenticated', 'public.purgar_contadores(date)', 'execute') then
    raise exception 'anon/authenticated pueden ejecutar las funciones';
  end if;

  -- Sin columnas de datos personales: solo fecha, métrica, origen y cantidad
  select count(*) into n from information_schema.columns where table_schema = 'public' and table_name = 'contadores_diarios'
     and column_name not in ('fecha', 'metrica', 'origen', 'cantidad');
  if n <> 0 then raise exception 'columnas no permitidas en contadores_diarios'; end if;
  select count(*) into n from information_schema.columns where table_schema = 'public' and table_name = 'contadores_diarios';
  if n <> 4 then raise exception 'columnas esperadas 4, hay %', n; end if;
  -- origen es obligatorio con valor por defecto 'general'
  insert into public.contadores_diarios(fecha, metrica) values (hoy, 'whatsapp_enviados');
  select count(*) into n from public.contadores_diarios where fecha = hoy and metrica = 'whatsapp_enviados' and origen = 'general' and cantidad = 0;
  if n <> 1 then raise exception 'origen por defecto no es general'; end if;
  delete from public.contadores_diarios;

  -- Clave única (fecha, métrica, origen)
  insert into public.contadores_diarios(fecha, metrica, origen, cantidad) values (hoy, 'claude_llamadas', 'asistente', 1);
  begin
    insert into public.contadores_diarios(fecha, metrica, origen, cantidad) values (hoy, 'claude_llamadas', 'asistente', 1);
    raise exception 'fila duplicada aceptada';
  exception when unique_violation then null;
  end;
  -- Lista cerrada de métricas y cantidad no negativa
  begin
    insert into public.contadores_diarios(fecha, metrica, origen, cantidad) values (hoy, 'otra_metrica', 'general', 1);
    raise exception 'métrica fuera de lista aceptada';
  exception when check_violation then null;
  end;
  begin
    insert into public.contadores_diarios(fecha, metrica, origen, cantidad) values (hoy, 'whatsapp_enviados', 'general', -1);
    raise exception 'cantidad negativa aceptada';
  exception when check_violation then null;
  end;
  delete from public.contadores_diarios;

  -- Incremento: crea y suma; el contador de hoy en 10 + incrementos de 1 y de 2 = 13
  total := public.incrementar_contador(hoy, 'brevo_correos_enviados', 'general', 10);
  if total <> 10 then raise exception 'primer incremento: % (esperado 10)', total; end if;
  perform public.incrementar_contador(hoy, 'brevo_correos_enviados', 'general', 1);
  total := public.incrementar_contador(hoy, 'brevo_correos_enviados', 'general', 2);
  if total <> 13 then raise exception 'incrementos: % (esperado 13)', total; end if;
  begin
    perform public.incrementar_contador(hoy, 'brevo_correos_enviados', 'general', -1);
    raise exception 'incremento negativo aceptado';
  exception when raise_exception then
    if sqlerrm <> 'cantidad inválida' then raise; end if;
  end;
  delete from public.contadores_diarios;

  -- Purga: solo fecha < hoy - 90; deja la marca; la segunda del mismo día no purga
  insert into public.contadores_diarios(fecha, metrica, origen, cantidad) values
    (hoy - 91, 'claude_llamadas', 'whatsapp', 5), (hoy - 200, 'purga', 'general', 0),
    (hoy - 90, 'claude_llamadas', 'whatsapp', 5), (hoy - 1, 'whatsapp_recibidos', 'general', 3);
  r := public.purgar_contadores(hoy);
  if r <> 2 then raise exception 'purga borró % filas (esperado 2)', r; end if;
  select count(*) into n from public.contadores_diarios where fecha < hoy - 90;
  if n <> 0 then raise exception 'quedaron filas anteriores a 90 días'; end if;
  select count(*) into n from public.contadores_diarios where fecha >= hoy - 90 and metrica <> 'purga';
  if n <> 2 then raise exception 'la purga borró filas vigentes'; end if;
  select count(*) into n from public.contadores_diarios where fecha = hoy and metrica = 'purga' and origen = 'general';
  if n <> 1 then raise exception 'falta la marca de purga'; end if;
  insert into public.contadores_diarios(fecha, metrica, origen, cantidad) values (hoy - 120, 'claude_llamadas', 'whatsapp', 1);
  r := public.purgar_contadores(hoy);
  if r <> -1 then raise exception 'segunda purga del día devolvió % (esperado -1)', r; end if;
  select count(*) into n from public.contadores_diarios where fecha = hoy - 120;
  if n <> 1 then raise exception 'la segunda purga del día borró filas'; end if;
  delete from public.contadores_diarios;
  raise notice 'OK: contadores_diarios con RLS, clave única, incremento atómico y purga';
end $$;

-- CHG-017: tamano_bd() (después de 2026-11-24_monitor_tamano_bd.sql)
do $$
declare n bigint; t bigint;
begin
  select count(*) into n from pg_proc p join pg_namespace s on s.oid = p.pronamespace
   where s.nspname = 'public' and p.proname = 'tamano_bd' and p.pronargs = 0;
  if n <> 1 then raise exception 'falta public.tamano_bd()'; end if;
  t := public.tamano_bd();
  if t is null or t <= 0 then raise exception 'tamano_bd() devolvió % (esperado > 0)', t; end if;
  if has_function_privilege('anon', 'public.tamano_bd()', 'execute')
     or has_function_privilege('authenticated', 'public.tamano_bd()', 'execute') then
    raise exception 'anon/authenticated pueden ejecutar tamano_bd()';
  end if;
  raise notice 'OK: tamano_bd() existe, devuelve % bytes y solo service_role la ejecuta', t;
end $$;
