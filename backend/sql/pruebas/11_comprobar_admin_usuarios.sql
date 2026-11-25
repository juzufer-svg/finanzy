-- CHG-023 · INV-053 a INV-062: panel de administración de usuarios (después de 2026-11-25_admin_usuarios.sql, ejecutado dos veces)
-- La concurrencia real (sesiones simultáneas) está en probar.sh. Se ejecuta desde backend/sql/pruebas (usa \ir con ruta relativa).
-- Los usuarios de prueba tienen correo «adm_...@x.test» y un hash centinela que no puede aparecer en ninguna salida.

-- INV-062 · RLS y privilegios, propiedades de las funciones, columnas de la tabla de auditoría
do $$
declare n bigint; f text; cols text;
  funciones text[] := array[
    'public.admin_registrar_auditoria(text,uuid)', 'public.admin_listar_usuarios(text,integer,integer)',
    'public.admin_detalle_usuario(uuid)', 'public.admin_suspender_usuario(uuid)', 'public.admin_reactivar_usuario(uuid)',
    'public.admin_cerrar_sesiones_usuario(uuid)', 'public.admin_eliminar_usuario(uuid,text)', 'public.admin_auditoria(integer,integer)',
    'public.registrar_acceso(uuid)'];
  lectura text[] := array['public.admin_listar_usuarios(text,integer,integer)', 'public.admin_detalle_usuario(uuid)', 'public.admin_auditoria(integer,integer)'];
begin
  select count(*) into n from pg_tables where schemaname = 'public' and tablename = 'auditoria_admin' and rowsecurity;
  if n <> 1 then raise exception 'auditoria_admin sin RLS'; end if;
  select count(*) into n from pg_policies where schemaname = 'public' and tablename = 'auditoria_admin';
  if n <> 0 then raise exception 'auditoria_admin no debe tener políticas (hay %)', n; end if;
  if has_table_privilege('anon', 'public.auditoria_admin', 'select,insert,update,delete')
     or has_table_privilege('authenticated', 'public.auditoria_admin', 'select,insert,update,delete')
     or has_table_privilege('anon', 'public.auditoria_admin', 'select')
     or has_table_privilege('authenticated', 'public.auditoria_admin', 'select') then
    raise exception 'anon/authenticated tienen acceso a auditoria_admin';
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role')
     and not has_table_privilege('service_role', 'public.auditoria_admin', 'select,insert,update,delete') then
    raise exception 'service_role no tiene acceso a auditoria_admin';
  end if;
  -- Sin datos personales: solo estas 4 columnas, y sin llave foránea
  select string_agg(column_name, ',' order by column_name) into cols
    from information_schema.columns where table_schema = 'public' and table_name = 'auditoria_admin';
  if cols <> 'accion,creado_en,id,usuario_id' then raise exception 'columnas de auditoria_admin: %', cols; end if;
  select count(*) into n from pg_constraint where conrelid = 'public.auditoria_admin'::regclass and contype = 'f';
  if n <> 0 then raise exception 'auditoria_admin no debe tener llaves foráneas'; end if;
  select count(*) into n from pg_indexes where schemaname = 'public' and tablename = 'auditoria_admin' and indexname = 'idx_auditoria_admin_creado';
  if n <> 1 then raise exception 'falta el índice de auditoria_admin'; end if;

  foreach f in array funciones loop
    if to_regprocedure(f) is null then raise exception 'falta la función %', f; end if;
    if has_function_privilege('anon', f, 'execute') or has_function_privilege('authenticated', f, 'execute') then
      raise exception 'anon/authenticated pueden ejecutar %', f;
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') and not has_function_privilege('service_role', f, 'execute') then
      raise exception 'service_role no puede ejecutar %', f;
    end if;
    select count(*) into n from pg_proc p, aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
     where p.oid = to_regprocedure(f) and a.grantee = 0 and a.privilege_type = 'EXECUTE';
    if n <> 0 then raise exception 'PUBLIC puede ejecutar %', f; end if;
    select count(*) into n from pg_proc p
     where p.oid = to_regprocedure(f) and not p.prosecdef and exists (select 1 from unnest(p.proconfig) c where c like 'search_path=%');
    if n <> 1 then raise exception '% debe ser SECURITY INVOKER con search_path fijo', f; end if;
    -- las de lectura son STABLE; las demás, no
    select count(*) into n from pg_proc p where p.oid = to_regprocedure(f) and p.provolatile = 's';
    if (f = any(lectura)) and n <> 1 then raise exception '% debe ser STABLE', f; end if;
    if not (f = any(lectura)) and n <> 0 then raise exception '% no debe ser STABLE', f; end if;
  end loop;
  select count(*) into n from pg_proc p join pg_namespace s on s.oid = p.pronamespace
   where s.nspname = 'public' and (p.proname like 'admin\_%' or p.proname = 'registrar_acceso');
  if n <> 9 then raise exception 'se esperaban 9 funciones del panel, hay %', n; end if;
  raise notice 'OK: INV-062 RLS sin políticas, permisos, columnas, STABLE e INVOKER';
end $$;

-- INV-062 · idempotencia: una tercera ejecución no cambia ninguna fila existente ni pierde marcas
do $$
declare n bigint; u uuid;
begin
  select count(*) into n from public.users where suspendida or ultimo_acceso is not null;
  if n <> 0 then raise exception 'filas anteriores de users con marcas nuevas: %', n; end if;
  insert into public.users (email, hashed_password, full_name, is_active, currency, session_version)
    values ('adm_idem@x.test', 'HASH_SECRETO_NO_SALE', 'Idem', true, 'COP', 7) returning id into u;
  update public.users set suspendida = true, ultimo_acceso = timestamptz '2026-01-02 03:04:05+00' where id = u;
end $$;
\ir ../2026-11-25_admin_usuarios.sql
do $$
declare r record;
begin
  select suspendida, ultimo_acceso, session_version, is_active into r from public.users where email = 'adm_idem@x.test';
  if not r.suspendida or r.ultimo_acceso <> timestamptz '2026-01-02 03:04:05+00' or r.session_version <> 7 or not r.is_active then
    raise exception 'repetir la migración cambió una fila existente';
  end if;
  delete from public.users where email = 'adm_idem@x.test';
  delete from public.auditoria_admin;
  raise notice 'OK: INV-062 idempotencia';
end $$;

-- Datos de prueba: 3 usuarios con datos de todas las tablas (textos e importes centinela)
do $$
declare a uuid; b uuid; c uuid; cat uuid; tr uuid;
begin
  insert into public.users (email, hashed_password, full_name, is_active, currency, created_at) values
    ('adm_ana@x.test', 'HASH_SECRETO_NO_SALE', 'Ana Pérez', true, 'COP', timestamp '2026-11-20 10:00:00') returning id into a;
  insert into public.users (email, hashed_password, full_name, is_active, currency, created_at) values
    ('adm_beto@x.test', 'HASH_SECRETO_NO_SALE', 'Beto 100%_x', true, 'USD', timestamp '2026-11-21 10:00:00') returning id into b;
  insert into public.users (email, hashed_password, full_name, is_active, currency, created_at) values
    ('adm_pend@x.test', 'HASH_SECRETO_NO_SALE', null, false, 'EUR', timestamp '2026-11-22 10:00:00') returning id into c;
  insert into public.categorias (usuario_id, nombre, icono, tipo) values (a, 'CATEGORIA_CENTINELA', 'x', 'gasto') returning id into cat;
  insert into public.transacciones (usuario_id, categoria_id, monto, descripcion, fecha, tipo)
    values (a, cat, 987654.32, 'DESCRIPCION_CENTINELA', current_date, 'gasto'), (a, cat, 1.11, 'otra', current_date, 'gasto');
  insert into public.metas (usuario_id, nombre, monto_objetivo, monto_actual, fecha_objetivo, estado) values (a, 'META_CENTINELA', 5555555, 1, current_date, 'activa');
  insert into public.presupuestos (usuario_id, categoria_id, limite_mensual, mes_ano) values (a, cat, 777777, '2026-11');
  insert into public.recurrentes (usuario_id, tipo, monto, descripcion, frecuencia, dia_ancla, proxima_fecha)
    values (a, 'gasto', 123456, 'RECURRENTE_CENTINELA', 'mensual', 5, current_date);
  insert into public.whatsapp_enlaces (usuario_id, telefono) values (a, '+573001112233');
  insert into public.whatsapp_mensajes (id, usuario_id) values ('wamid.adm1', a);
  select id into tr from public.transacciones where usuario_id = a limit 1;
  insert into public.whatsapp_registros (transaccion_id, usuario_id, lote) values (tr, a, 'wamid.adm1');
end $$;

-- INV-055 · el jsonb de lista, detalle y auditoría solo trae las claves permitidas y nunca datos sensibles ni financieros
do $$
declare lista jsonb; det jsonb; aud jsonb; k text; a uuid; permitidas text[] := array[
  'generado_en','total','usuarios','id','correo','nombre','estado','moneda','registrado_en','ultimo_acceso','uso',
  'transacciones','categorias','presupuestos','metas','recurrentes','whatsapp_conectado','registros','fecha','accion','usuario_id','usuario_correo'];
begin
  select id into a from public.users where email = 'adm_ana@x.test';
  lista := public.admin_listar_usuarios(null, 25, 0);
  det := public.admin_detalle_usuario(a);
  perform public.admin_cerrar_sesiones_usuario(a);
  aud := public.admin_auditoria(25, 0);
  for k in select distinct jsonb_object_keys(o) from (
      select jsonb_path_query(lista, 'lax $.** ? (@.type() == "object")') as o
      union all select jsonb_path_query(det, 'lax $.** ? (@.type() == "object")')
      union all select jsonb_path_query(aud, 'lax $.** ? (@.type() == "object")')) s loop
    if not (k = any(permitidas)) then raise exception 'clave no permitida en el jsonb: %', k; end if;
  end loop;
  if (lista::text || det::text || aud::text) ~* 'hashed_password|HASH_SECRETO|session_version|CENTINELA|987654|5555555|777777|123456|573001112233|monto|descripcion' then
    raise exception 'el jsonb filtra datos sensibles o financieros';
  end if;
  if jsonb_typeof(det -> 'uso' -> 'transacciones') <> 'number' or jsonb_typeof(det -> 'uso' -> 'whatsapp_conectado') <> 'boolean' then
    raise exception 'el uso debe ser conteos y un booleano';
  end if;
  if (det -> 'uso' ->> 'transacciones') <> '2' or (det -> 'uso' ->> 'categorias') <> '1' or (det -> 'uso' ->> 'metas') <> '1'
     or (det -> 'uso' ->> 'presupuestos') <> '1' or (det -> 'uso' ->> 'recurrentes') <> '1' or (det -> 'uso' ->> 'whatsapp_conectado') <> 'true' then
    raise exception 'conteos de uso incorrectos: %', det -> 'uso';
  end if;
  if (select count(*) from jsonb_object_keys(lista -> 'usuarios' -> 0 -> 'uso')) <> 1 then raise exception 'la lista solo cuenta transacciones'; end if;
  delete from public.auditoria_admin;
  raise notice 'OK: INV-055 jsonb sin claves sensibles';
end $$;

-- INV-060 · lista: formato, orden, paginación, tiempos en UTC con Z, búsqueda literal
do $$
declare r jsonb; n integer;
begin
  r := public.admin_listar_usuarios(null, 25, 0);
  if (r ->> 'total')::int <> (select count(*) from public.users) then raise exception 'total incorrecto'; end if;
  -- orden: registrado_en descendente
  if (r -> 'usuarios' -> 0 ->> 'correo') <> 'adm_pend@x.test' then raise exception 'el primero debía ser el más reciente: %', r -> 'usuarios' -> 0 ->> 'correo'; end if;
  if (r -> 'usuarios' -> 0 ->> 'registrado_en') <> '2026-11-22T10:00:00Z' then raise exception 'fecha sin Z/UTC: %', r -> 'usuarios' -> 0 ->> 'registrado_en'; end if;
  if (r -> 'usuarios' -> 0 ->> 'estado') <> 'pendiente' or (r -> 'usuarios' -> 1 ->> 'estado') <> 'activa' then raise exception 'estados incorrectos'; end if;
  if (r -> 'usuarios' -> 0 -> 'ultimo_acceso') <> 'null'::jsonb then raise exception 'ultimo_acceso debía ser null'; end if;
  -- búsqueda: sin distinguir mayúsculas, por correo o nombre
  r := public.admin_listar_usuarios('ANA', 25, 0);
  if (r ->> 'total')::int <> 1 or (r -> 'usuarios' -> 0 ->> 'correo') <> 'adm_ana@x.test' then raise exception 'buscar ANA: %', r ->> 'total'; end if;
  r := public.admin_listar_usuarios('pérez', 25, 0);
  if (r ->> 'total')::int <> 1 then raise exception 'buscar por nombre'; end if;
  -- comodines y comillas son texto literal
  r := public.admin_listar_usuarios('%', 25, 0);
  if (r ->> 'total')::int <> 1 or (r -> 'usuarios' -> 0 ->> 'correo') <> 'adm_beto@x.test' then raise exception '«%%» debía coincidir solo con el nombre que lo contiene'; end if;
  r := public.admin_listar_usuarios('_', 25, 0);
  select count(*) into n from jsonb_array_elements(r -> 'usuarios') x where x ->> 'correo' not like '%\_%' and (x ->> 'nombre') not like '%\_%';
  if n <> 0 or (r ->> 'total')::int < 1 then raise exception '«_» debía ser literal'; end if;
  r := public.admin_listar_usuarios(chr(92), 25, 0);
  if (r ->> 'total')::int <> 0 then raise exception 'la barra invertida debía ser literal (coincidió con %)', r ->> 'total'; end if;
  r := public.admin_listar_usuarios('100%_', 25, 0);
  if (r ->> 'total')::int <> 1 then raise exception '«100%%_» literal'; end if;
  r := public.admin_listar_usuarios('%_x', 25, 0);
  if (r ->> 'total')::int <> 1 then raise exception 'comodines combinados'; end if;
  foreach r in array array[public.admin_listar_usuarios('''; drop table users; --', 25, 0), public.admin_listar_usuarios(''' or 1=1 --', 25, 0),
                           public.admin_listar_usuarios('a,id.eq.1)', 25, 0)] loop
    if (r ->> 'total')::int <> 0 then raise exception 'una carga de inyección coincidió con algo'; end if;
  end loop;
  if to_regclass('public.users') is null then raise exception 'users no debía desaparecer'; end if;
  begin perform public.admin_listar_usuarios(repeat('a', 61), 25, 0); raise exception 'debía fallar con 61 caracteres';
  exception when raise_exception then if sqlerrm like 'debía fallar%' then raise; end if; end;
  -- límites acotados
  r := public.admin_listar_usuarios(null, 1000, -5);
  if jsonb_array_length(r -> 'usuarios') > 25 then raise exception 'el límite debe acotarse a 25'; end if;
  r := public.admin_listar_usuarios(null, 1, 1);
  if jsonb_array_length(r -> 'usuarios') <> 1 then raise exception 'desplazamiento'; end if;
  raise notice 'OK: INV-060 lista, orden, tiempos y búsqueda literal';
end $$;

-- INV-062 · funciones de solo lectura: no escriben (llamadas dentro de una transacción de solo lectura)
begin read only;
do $$ declare a uuid; begin
  select id into a from public.users where email = 'adm_ana@x.test';
  perform public.admin_listar_usuarios('ana', 25, 0);
  perform public.admin_detalle_usuario(a);
  perform public.admin_auditoria(25, 0);
  raise notice 'OK: INV-062 funciones de solo lectura (read only)';
end $$;
-- y una de escritura debe fallar en solo lectura (comprueba que la prueba sí detecta escrituras)
do $$ declare a uuid; begin
  select id into a from public.users where email = 'adm_ana@x.test';
  begin perform public.admin_suspender_usuario(a); raise exception 'la escritura debía fallar en solo lectura';
  exception when read_only_sql_transaction then null; end;
end $$;
rollback;

-- INV-056 / INV-057 · suspender, reactivar y cerrar sesiones (estados, efectos y auditoría), ejecutado COMO service_role
do $$
declare a uuid; b uuid; c uuid; sv0 integer; sv1 integer; r text; n bigint; ra record;
begin
  select id into a from public.users where email = 'adm_ana@x.test';
  select id into c from public.users where email = 'adm_pend@x.test';
  insert into public.whatsapp_enlaces (usuario_id, telefono) values (a, '+573001112233') on conflict do nothing;   -- el bloque INV-055 cerró sus sesiones (borra el enlace)
  select session_version into sv0 from public.users where id = a;
  if exists (select 1 from pg_roles where rolname = 'service_role') then set local role service_role; end if;

  -- pendiente → pendiente (sin cambios ni auditoría); inexistente → no_existe
  if public.admin_suspender_usuario(c) <> 'pendiente' then raise exception 'suspender pendiente'; end if;
  if public.admin_suspender_usuario(gen_random_uuid()) <> 'no_existe' then raise exception 'suspender inexistente'; end if;
  if public.admin_reactivar_usuario(gen_random_uuid()) <> 'no_existe' then raise exception 'reactivar inexistente'; end if;
  if public.admin_cerrar_sesiones_usuario(gen_random_uuid()) <> 'no_existe' then raise exception 'cerrar inexistente'; end if;
  if public.admin_eliminar_usuario(gen_random_uuid(), 'x@x.test') <> 'no_existe' then raise exception 'eliminar inexistente'; end if;
  select count(*) into n from public.auditoria_admin;
  if n <> 0 then raise exception 'lo rechazado no debe auditarse (hay %)', n; end if;
  if public.admin_reactivar_usuario(a) <> 'no_suspendida' then raise exception 'reactivar no suspendida'; end if;

  -- suspender: marca, versión +1, borra WhatsApp, una fila de auditoría; la segunda vez es «ya»
  if public.admin_suspender_usuario(a) <> 'ok' then raise exception 'suspender'; end if;
  select suspendida, session_version into ra from public.users where id = a;
  if not ra.suspendida or ra.session_version <> sv0 + 1 then raise exception 'suspender: marca/versión %/%', ra.suspendida, ra.session_version; end if;
  if exists (select 1 from public.whatsapp_enlaces where usuario_id = a) then raise exception 'suspender debía borrar el enlace de WhatsApp'; end if;
  if public.admin_suspender_usuario(a) <> 'ya' then raise exception 'suspender dos veces'; end if;
  select count(*) into n from public.auditoria_admin where usuario_id = a and accion = 'suspender';
  if n <> 1 then raise exception 'suspender: % filas de auditoría', n; end if;
  if (public.admin_detalle_usuario(a) ->> 'estado') <> 'suspendida' then raise exception 'estado suspendida'; end if;
  -- cerrar sesiones sobre una suspendida: +1 exacto
  if public.admin_cerrar_sesiones_usuario(a) <> 'ok' then raise exception 'cerrar'; end if;
  select session_version into sv1 from public.users where id = a;
  if sv1 <> sv0 + 2 then raise exception 'cerrar sesiones debía subir exactamente 1 (de % a %)', sv0 + 1, sv1; end if;
  -- reactivar: solo quita la marca; la versión no baja
  if public.admin_reactivar_usuario(a) <> 'ok' then raise exception 'reactivar'; end if;
  select suspendida, session_version into ra from public.users where id = a;
  if ra.suspendida or ra.session_version <> sv0 + 2 then raise exception 'reactivar no debe bajar la versión'; end if;
  if (public.admin_detalle_usuario(a) ->> 'estado') <> 'activa' then raise exception 'estado activa'; end if;
  if public.admin_reactivar_usuario(a) <> 'no_suspendida' then raise exception 'reactivar dos veces'; end if;
  select count(*) into n from public.auditoria_admin;
  if n <> 3 then raise exception 'se esperaban 3 registros (suspender, cerrar_sesiones, reactivar), hay %', n; end if;
  -- la baja confirma el correo (mayúsculas y espacios); uno distinto no cambia nada
  if public.admin_eliminar_usuario(c, 'otro@x.test') <> 'correo_distinto' then raise exception 'correo distinto'; end if;
  if not exists (select 1 from public.users where id = c) then raise exception 'correo distinto no debe borrar'; end if;
  if (select count(*) from public.auditoria_admin) <> 3 then raise exception 'correo distinto no debe auditar'; end if;
  reset role;
  -- registrar_acceso: escribe la primera vez y no la segunda (menos de una hora); a la hora y un segundo vuelve a escribir
  update public.users set ultimo_acceso = null where id = a;
  if exists (select 1 from pg_roles where rolname = 'service_role') then set local role service_role; end if;
  if not public.registrar_acceso(a) then raise exception 'registrar_acceso debía escribir la primera vez'; end if;
  if public.registrar_acceso(a) then raise exception 'registrar_acceso no debía escribir dos veces en una hora'; end if;
  reset role;
  update public.users set ultimo_acceso = now() - interval '59 minutes' where id = a;
  if public.registrar_acceso(a) then raise exception 'a los 59 minutos no debía escribir'; end if;
  update public.users set ultimo_acceso = now() - interval '61 minutes' where id = a;
  if not public.registrar_acceso(a) then raise exception 'a los 61 minutos debía escribir'; end if;
  if public.registrar_acceso(gen_random_uuid()) then raise exception 'usuario inexistente no escribe'; end if;
  delete from public.auditoria_admin;
  raise notice 'OK: INV-056/057/061 acciones, estados y último acceso (como service_role)';
end $$;

-- INV-059 · atomicidad: si la auditoría falla, la acción se revierte (no hay acción sin registro)
do $$
declare a uuid; sv0 integer; r text;
begin
  select id into a from public.users where email = 'adm_ana@x.test';
  insert into public.whatsapp_enlaces (usuario_id, telefono) values (a, '+573001112233') on conflict do nothing;   -- la suspensión de arriba lo borró
  select session_version into sv0 from public.users where id = a;
  create function public.zz_falla_auditoria() returns trigger language plpgsql as $f$ begin raise exception 'fallo simulado de auditoría'; end $f$;
  create trigger zz_falla before insert on public.auditoria_admin for each row execute function public.zz_falla_auditoria();
  begin perform public.admin_suspender_usuario(a); raise exception 'debía fallar';
  exception when others then if sqlerrm not like 'fallo simulado%' then raise; end if; end;
  begin perform public.admin_cerrar_sesiones_usuario(a); raise exception 'debía fallar';
  exception when others then if sqlerrm not like 'fallo simulado%' then raise; end if; end;
  begin perform public.admin_eliminar_usuario(a, 'adm_ana@x.test'); raise exception 'debía fallar';
  exception when others then if sqlerrm not like 'fallo simulado%' then raise; end if; end;
  drop trigger zz_falla on public.auditoria_admin;
  drop function public.zz_falla_auditoria();
  if exists (select 1 from public.users where id = a and (suspendida or session_version <> sv0)) then raise exception 'la acción no se revirtió'; end if;
  if not exists (select 1 from public.users where id = a) then raise exception 'la baja no se revirtió'; end if;
  if not exists (select 1 from public.whatsapp_enlaces where usuario_id = a) then raise exception 'el enlace de WhatsApp no se revirtió'; end if;
  if exists (select 1 from public.auditoria_admin) then raise exception 'quedó un registro'; end if;
  raise notice 'OK: INV-059 acción y registro atómicos';
end $$;

-- INV-059 · retención de 365 días y tope de 10 000 filas (solo se aplican al superarse)
do $$
declare n bigint;
begin
  delete from public.auditoria_admin;
  insert into public.auditoria_admin (creado_en, accion, usuario_id) select now() - interval '366 days' - (g || ' minutes')::interval, 'suspender', gen_random_uuid() from generate_series(1, 5) g;
  insert into public.auditoria_admin (creado_en, accion, usuario_id) select now() - interval '364 days', 'reactivar', gen_random_uuid();
  perform public.admin_registrar_auditoria('suspender', gen_random_uuid());
  select count(*) into n from public.auditoria_admin;
  if n <> 2 then raise exception 'la retención debía dejar 2 filas (364 días y la nueva), hay %', n; end if;
  -- tope: 10 005 filas + 1 nueva → quedan exactamente 10 000 y se conservan las más recientes
  delete from public.auditoria_admin;
  insert into public.auditoria_admin (creado_en, accion, usuario_id) select now() - (g || ' seconds')::interval - interval '1 minute', 'suspender', gen_random_uuid() from generate_series(1, 10005) g;
  perform public.admin_registrar_auditoria('eliminar', gen_random_uuid());
  select count(*) into n from public.auditoria_admin;
  if n <> 10000 then raise exception 'el tope debía dejar 10000 filas, hay %', n; end if;
  if (select accion from public.auditoria_admin order by creado_en desc, id desc limit 1) <> 'eliminar' then raise exception 'se conservan las más recientes'; end if;
  if (select max(creado_en) - min(creado_en) from public.auditoria_admin) > interval '10000 seconds' + interval '2 minutes' then raise exception 'se borraron las más recientes'; end if;
  -- por debajo del tope no se borra nada (ni se cuenta de más)
  delete from public.auditoria_admin;
  insert into public.auditoria_admin (accion, usuario_id) select 'suspender', gen_random_uuid() from generate_series(1, 9990);
  perform public.admin_registrar_auditoria('suspender', gen_random_uuid());
  select count(*) into n from public.auditoria_admin;
  if n <> 9991 then raise exception 'sin superar el tope no se borra nada (hay %)', n; end if;
  -- una acción no válida se rechaza por la restricción de la tabla
  begin perform public.admin_registrar_auditoria('inventada', gen_random_uuid()); raise exception 'debía fallar';
  exception when check_violation then null; end;
  delete from public.auditoria_admin;
  raise notice 'OK: INV-059 retención de 365 días y tope de 10000 filas';
end $$;

-- INV-058 · baja con datos en todas las tablas: una sola fila de auditoría, cascada completa, el registro sobrevive y sin correo
do $$
declare a uuid; n bigint; r jsonb; t text;
begin
  select id into a from public.users where email = 'adm_ana@x.test';
  if public.admin_eliminar_usuario(a, '  ADM_ANA@X.TEST ') <> 'ok' then raise exception 'eliminar con mayúsculas y espacios'; end if;
  foreach t in array array['users', 'categorias', 'transacciones', 'presupuestos', 'metas', 'recurrentes', 'whatsapp_enlaces', 'whatsapp_mensajes', 'whatsapp_registros'] loop
    execute format('select count(*) from public.%I where %s = $1', t, case t when 'users' then 'id' else 'usuario_id' end) into n using a;
    if n <> 0 then raise exception 'la baja dejó % filas en %', n, t; end if;
  end loop;
  select count(*) into n from public.auditoria_admin where usuario_id = a and accion = 'eliminar';
  if n <> 1 or (select count(*) from public.auditoria_admin) <> 1 then raise exception 'la baja debía dejar una sola fila de auditoría'; end if;
  r := public.admin_auditoria(25, 0);
  if (r -> 'registros' -> 0 -> 'usuario_correo') <> 'null'::jsonb or (r -> 'registros' -> 0 ->> 'accion') <> 'eliminar'
     or (r -> 'registros' -> 0 ->> 'usuario_id') <> a::text or (r -> 'registros' -> 0 ->> 'fecha') !~ '^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$' then
    raise exception 'el registro debía sobrevivir sin correo: %', r -> 'registros' -> 0;
  end if;
  if public.admin_detalle_usuario(a) is not null then raise exception 'el detalle de una cuenta borrada debía ser null'; end if;
  -- mientras la cuenta existe, el correo sí se une al leer
  perform public.admin_cerrar_sesiones_usuario((select id from public.users where email = 'adm_beto@x.test'));
  r := public.admin_auditoria(25, 0);
  if (r -> 'registros' -> 0 ->> 'usuario_correo') <> 'adm_beto@x.test' or (r -> 'registros' -> 1 -> 'usuario_correo') <> 'null'::jsonb then
    raise exception 'orden o unión del correo incorrectos: %', r -> 'registros';
  end if;
  raise notice 'OK: INV-058/059 baja con cascada, auditoría que sobrevive';
end $$;

-- INV-062 · 1 000 usuarios con ~200 filas cada uno: la lista responde en menos de 2 s (REQ-N-027)
do $$
declare t0 timestamptz; ms numeric; r jsonb;
begin
  insert into public.users (email, hashed_password, full_name, is_active, currency, created_at)
    select 'adm_masivo' || g || '@x.test', 'HASH_SECRETO_NO_SALE', 'Masivo ' || g, true, 'COP', timestamp '2026-01-01' + (g || ' minutes')::interval from generate_series(1, 1000) g;
  insert into public.categorias (usuario_id, nombre, icono, tipo)
    select u.id, 'c' || g, 'x', 'gasto' from public.users u, generate_series(1, 20) g where u.email like 'adm\_masivo%';
  insert into public.transacciones (usuario_id, categoria_id, monto, descripcion, fecha, tipo)
    select u.id, null, 10, 'd', current_date, 'gasto' from public.users u, generate_series(1, 120) g where u.email like 'adm\_masivo%';
  insert into public.metas (usuario_id, nombre, monto_objetivo, monto_actual, fecha_objetivo, estado)
    select u.id, 'm' || g, 100, 0, current_date, 'activa' from public.users u, generate_series(1, 20) g where u.email like 'adm\_masivo%';
  insert into public.presupuestos (usuario_id, categoria_id, limite_mensual, mes_ano)
    select u.id, (select c.id from public.categorias c where c.usuario_id = u.id limit 1), 100, to_char(date '2020-01-01' + (g || ' months')::interval, 'YYYY-MM')
      from public.users u, generate_series(1, 20) g where u.email like 'adm\_masivo%';
  insert into public.recurrentes (usuario_id, tipo, monto, descripcion, frecuencia, dia_ancla, proxima_fecha)
    select u.id, 'gasto', 10, 'r', 'mensual', 5, current_date from public.users u, generate_series(1, 20) g where u.email like 'adm\_masivo%';
  analyze public.users; analyze public.transacciones; analyze public.categorias;
  t0 := clock_timestamp();
  r := public.admin_listar_usuarios(null, 25, 0);
  perform public.admin_listar_usuarios('masivo', 25, 975);
  perform public.admin_listar_usuarios('Masivo 99', 25, 0);
  ms := extract(epoch from clock_timestamp() - t0) * 1000;
  if (r ->> 'total')::int < 1000 or jsonb_array_length(r -> 'usuarios') <> 25 then raise exception 'lista de 1000 usuarios incorrecta'; end if;
  if ms > 2000 then raise exception 'las 3 listas con 1000 usuarios tardaron % ms (límite 2000)', ms; end if;
  if (public.admin_detalle_usuario((select id from public.users where email = 'adm_masivo7@x.test')) -> 'uso' ->> 'transacciones') <> '120' then raise exception 'detalle del masivo'; end if;
  delete from public.users where email like 'adm\_masivo%';
  raise notice 'OK: INV-062 1000 usuarios x ~200 filas: 3 listas en % ms', round(ms);
end $$;

-- Limpieza de los usuarios de prueba (probar.sh sigue con la concurrencia sobre sus propios usuarios)
delete from public.users where email like 'adm\_%@x.test';
delete from public.auditoria_admin;
select 'OK: 11_comprobar_admin_usuarios' as resultado;
