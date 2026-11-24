-- CHG-020 · INV-037 a INV-041: estado de autenticación persistente (después de 2026-11-24_auth_persistente.sql, ejecutado dos veces)
-- Los casos con tiempo usan el parámetro p_ahora (solo existe para estas pruebas; el backend nunca lo envía).
-- La concurrencia real (sesiones simultáneas) está en probar.sh.

-- 1. RLS, políticas, permisos, columnas y propiedades de las funciones
do $$
declare n bigint; t text; f text;
  cols_esperadas jsonb := jsonb_build_object(
    'auth_login_intentos', 'actualizado_en,bloqueado_hasta,clave,en_vuelo,fallos,ultima_reserva,ventana_inicio',
    'auth_codigos', 'clave,codigo_hmac,emitido_en,expira_en,intentos,proposito',
    'auth_limites_eventos', 'clave,id,ocurrido_en,tipo');
  funciones text[] := array[
    'public.auth_login_reservar(text,integer,integer,integer,timestamptz)',
    'public.auth_login_resolver(text,boolean,integer,timestamptz)',
    'public.auth_login_reiniciar(text)',
    'public.auth_codigo_emitir(text,text,text,integer,integer,integer,integer,integer,timestamptz)',
    'public.auth_codigo_verificar(text,text,text,integer,timestamptz)',
    'public.auth_limite_registrar(text,text,integer,integer,timestamptz)',
    'public.auth_borrar_de_cuenta(text)',
    'public.auth_purgar(timestamptz,integer)'];
begin
  foreach t in array array['auth_login_intentos', 'auth_codigos', 'auth_limites_eventos'] loop
    select count(*) into n from pg_tables where schemaname = 'public' and tablename = t and rowsecurity;
    if n <> 1 then raise exception '% sin RLS', t; end if;
    select count(*) into n from pg_policies where schemaname = 'public' and tablename = t;
    if n <> 0 then raise exception '% no debe tener políticas (hay %)', t, n; end if;
    if has_table_privilege('anon', 'public.' || t, 'select,insert,update,delete')
       or has_table_privilege('authenticated', 'public.' || t, 'select,insert,update,delete')
       or has_table_privilege('anon', 'public.' || t, 'select') or has_table_privilege('authenticated', 'public.' || t, 'select') then
      raise exception 'anon/authenticated tienen acceso a %', t;
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role')
       and not has_table_privilege('service_role', 'public.' || t, 'select,insert,update,delete') then
      raise exception 'service_role no tiene acceso a %', t;
    end if;
    -- Solo las columnas previstas: ninguna de correo, IP ni código en claro
    select string_agg(column_name, ',' order by column_name) into f
      from information_schema.columns where table_schema = 'public' and table_name = t;
    if f <> cols_esperadas ->> t then raise exception 'columnas de %: % (esperadas %)', t, f, cols_esperadas ->> t; end if;
  end loop;

  foreach f in array funciones loop
    if to_regprocedure(f) is null then raise exception 'falta la función %', f; end if;
    if has_function_privilege('anon', f, 'execute') or has_function_privilege('authenticated', f, 'execute') then
      raise exception 'anon/authenticated pueden ejecutar %', f;
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role')
       and not has_function_privilege('service_role', f, 'execute') then
      raise exception 'service_role no puede ejecutar %', f;
    end if;
    -- public tampoco (has_function_privilege de un rol cualquiera sin membresías)
    select count(*) into n from pg_proc p, aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
     where p.oid = to_regprocedure(f) and a.grantee = 0 and a.privilege_type = 'EXECUTE';
    if n <> 0 then raise exception 'PUBLIC puede ejecutar %', f; end if;
    -- SECURITY INVOKER y search_path fijo
    select count(*) into n from pg_proc p
     where p.oid = to_regprocedure(f) and not p.prosecdef and exists (
       select 1 from unnest(p.proconfig) c where c like 'search_path=%');
    if n <> 1 then raise exception '% debe ser SECURITY INVOKER con search_path fijo', f; end if;
  end loop;
  select count(*) into n from pg_proc p join pg_namespace s on s.oid = p.pronamespace
   where s.nspname = 'public' and p.proname like 'auth\_%';
  if n <> 8 then raise exception 'se esperaban 8 funciones auth_*, hay %', n; end if;
  raise notice 'OK: auth persistente: RLS sin políticas, permisos, columnas y funciones SECURITY INVOKER';
end $$;

-- 2. Login: reservar / resolver / reiniciar
do $$
declare b timestamptz := now(); r record; f record; k text := 'k_login'; n integer; i integer;
begin
  delete from public.auth_login_intentos;
  -- 5 reservas: las 5 permitidas; la 5.ª fija el bloqueo de 15 min; la 6.ª se rechaza sin contar
  for i in 1..5 loop
    select * into r from public.auth_login_reservar(k, 5, 86400, 900, b + (i || ' seconds')::interval);
    if not r.permitido then raise exception 'la reserva % debía estar permitida', i; end if;
    if i < 5 and r.bloqueado_hasta is not null then raise exception 'bloqueo antes del 5.º'; end if;
  end loop;
  if r.bloqueado_hasta <> b + interval '5 seconds' + interval '15 minutes' then
    raise exception 'el bloqueo debe contar 15 min desde el 5.º (%)', r.bloqueado_hasta;
  end if;
  select * into r from public.auth_login_reservar(k, 5, 86400, 900, b + interval '6 seconds');
  if r.permitido then raise exception 'la 6.ª reserva debía rechazarse'; end if;
  select * into f from public.auth_login_intentos where clave = k;
  if f.fallos <> 5 or f.en_vuelo <> 5 then raise exception 'la reserva rechazada no debe contar (fallos %, en_vuelo %)', f.fallos, f.en_vuelo; end if;
  -- Bloqueado hasta justo antes de los 15 min; pasado el bloqueo la serie empieza de cero
  select * into r from public.auth_login_reservar(k, 5, 86400, 900, b + interval '5 seconds' + interval '899 seconds');
  if r.permitido then raise exception 'debía seguir bloqueado a los 899 s'; end if;
  select * into r from public.auth_login_reservar(k, 5, 86400, 900, b + interval '5 seconds' + interval '901 seconds');
  if not r.permitido or r.bloqueado_hasta is not null then raise exception 'tras el bloqueo debía permitir y empezar de cero'; end if;
  select * into f from public.auth_login_intentos where clave = k;
  if f.fallos <> 1 or f.en_vuelo <> 1 then raise exception 'la serie nueva debía empezar en 1 (fallos %, en_vuelo %)', f.fallos, f.en_vuelo; end if;
  delete from public.auth_login_intentos;

  -- Cinco fallos repartidos en menos de 24 h bloquean (08, 12, 16, 20 y 23 h): bloqueo contado desde el 5.º
  perform public.auth_login_reservar(k, 5, 86400, 900, b);
  perform public.auth_login_reservar(k, 5, 86400, 900, b + interval '4 hours');
  perform public.auth_login_reservar(k, 5, 86400, 900, b + interval '8 hours');
  perform public.auth_login_reservar(k, 5, 86400, 900, b + interval '12 hours');
  select * into r from public.auth_login_reservar(k, 5, 86400, 900, b + interval '15 hours');
  if r.bloqueado_hasta <> b + interval '15 hours' + interval '15 minutes' then raise exception 'bloqueo repartido en el día no fijado'; end if;
  delete from public.auth_login_intentos;

  -- Cuatro fallos de hace más de 24 h no acumulan con uno nuevo: sin bloqueo y la serie vuelve a 1
  for i in 1..4 loop perform public.auth_login_reservar(k, 5, 86400, 900, b + (i || ' minutes')::interval); end loop;
  select * into r from public.auth_login_reservar(k, 5, 86400, 900, b + interval '24 hours' + interval '61 seconds');
  if not r.permitido or r.bloqueado_hasta is not null then raise exception 'fallos de más de 24 h no deben bloquear'; end if;
  select * into f from public.auth_login_intentos where clave = k;
  if f.fallos <> 1 then raise exception 'la serie debía volver a 1 (hay %)', f.fallos; end if;
  -- Justo dentro de las 24 h desde el primer fallo sí acumulan
  delete from public.auth_login_intentos;
  for i in 1..4 loop perform public.auth_login_reservar(k, 5, 86400, 900, b + (i || ' minutes')::interval); end loop;
  select * into r from public.auth_login_reservar(k, 5, 86400, 900, b + interval '23 hours 59 minutes');
  if r.bloqueado_hasta is null then raise exception 'a las 23 h 59 min del primero el 5.º debía bloquear'; end if;
  delete from public.auth_login_intentos;

  -- Resolver con fallo: solo baja en_vuelo; el fallo ya estaba contado
  perform public.auth_login_reservar(k, 5, 86400, 900, b);
  perform public.auth_login_resolver(k, false, 5, b);
  select * into f from public.auth_login_intentos where clave = k;
  if f.fallos <> 1 or f.en_vuelo <> 0 then raise exception 'resolver(false): fallos %, en_vuelo %', f.fallos, f.en_vuelo; end if;
  -- Resolver con acierto y nada en vuelo: borra la serie
  perform public.auth_login_reservar(k, 5, 86400, 900, b);
  perform public.auth_login_reservar(k, 5, 86400, 900, b);
  perform public.auth_login_resolver(k, false, 5, b);
  perform public.auth_login_resolver(k, false, 5, b);
  perform public.auth_login_reservar(k, 5, 86400, 900, b);        -- 3 fallos resueltos + esta reserva = 4 (0 + 3 anteriores)
  perform public.auth_login_resolver(k, true, 5, b);
  select count(*) into n from public.auth_login_intentos where clave = k;
  if n <> 0 then raise exception 'login correcto sin reservas en vuelo debía borrar la serie'; end if;
  -- Resolver con acierto con reservas en vuelo: devuelve solo su intento, no borra los fallos en vuelo
  for i in 1..3 loop perform public.auth_login_reservar(k, 5, 86400, 900, b); end loop;   -- 3 en vuelo
  perform public.auth_login_reservar(k, 5, 86400, 900, b);                                -- la que acierta
  perform public.auth_login_resolver(k, true, 5, b);
  select * into f from public.auth_login_intentos where clave = k;
  if f.fallos <> 3 or f.en_vuelo <> 3 then raise exception 'devolver el intento: fallos %, en_vuelo % (esperado 3 y 3)', f.fallos, f.en_vuelo; end if;
  delete from public.auth_login_intentos;

  -- La 5.ª reserva que acierta: levanta el bloqueo que fijó ella misma y el correo queda desbloqueado
  for i in 1..4 loop perform public.auth_login_reservar(k, 5, 86400, 900, b); end loop;   -- 4 en vuelo
  select * into r from public.auth_login_reservar(k, 5, 86400, 900, b);                   -- la 5.ª: fija el bloqueo
  if r.bloqueado_hasta is null then raise exception 'la 5.ª debía fijar el bloqueo'; end if;
  perform public.auth_login_resolver(k, true, 5, b);
  select * into f from public.auth_login_intentos where clave = k;
  if f.fallos <> 4 or f.bloqueado_hasta is not null or f.en_vuelo <> 4 then
    raise exception 'la 5.ª que acierta: fallos %, bloqueo %, en_vuelo %', f.fallos, f.bloqueado_hasta, f.en_vuelo;
  end if;
  -- Las 4 restantes fallan: sigue la serie con 4 fallos y el siguiente fallo bloquea
  for i in 1..4 loop perform public.auth_login_resolver(k, false, 5, b); end loop;
  select * into r from public.auth_login_reservar(k, 5, 86400, 900, b);
  if not r.permitido or r.bloqueado_hasta is null then raise exception 'el siguiente fallo debía volver a bloquear'; end if;
  delete from public.auth_login_intentos;
  -- Sin nada en vuelo (4 resueltos): la 5.ª que acierta deja el correo desbloqueado y sin serie
  for i in 1..4 loop perform public.auth_login_reservar(k, 5, 86400, 900, b); perform public.auth_login_resolver(k, false, 5, b); end loop;
  perform public.auth_login_reservar(k, 5, 86400, 900, b);
  perform public.auth_login_resolver(k, true, 5, b);
  select * into r from public.auth_login_reservar(k, 5, 86400, 900, b);
  if not r.permitido or r.bloqueado_hasta is not null then raise exception 'tras la 5.ª que acierta el correo debía quedar libre'; end if;
  delete from public.auth_login_intentos;

  -- I-1: una reserva que nunca se resolvió (despliegue, plazo vencido, ejecutor lleno) no impide que un login correcto
  -- reinicie la serie pasados 10 s: la serie se borra y hacen falta 5 fallos NUEVOS para bloquear
  perform public.auth_login_reservar(k, 5, 86400, 900, b);                                  -- huérfana: nunca se resuelve
  select * into f from public.auth_login_intentos where clave = k;
  if f.en_vuelo <> 1 or f.ultima_reserva <> b then raise exception 'la reserva debía quedar en vuelo con su hora (%, %)', f.en_vuelo, f.ultima_reserva; end if;
  perform public.auth_login_reservar(k, 5, 86400, 900, b + interval '30 seconds');          -- el login correcto
  select * into f from public.auth_login_intentos where clave = k;
  if f.fallos <> 2 or f.en_vuelo <> 1 then raise exception 'la huérfana de hace 30 s no debía contar en vuelo (fallos %, en_vuelo %)', f.fallos, f.en_vuelo; end if;
  perform public.auth_login_resolver(k, true, 5, b + interval '31 seconds');
  select count(*) into n from public.auth_login_intentos where clave = k;
  if n <> 0 then raise exception 'con una huérfana de hace más de 10 s el login correcto debía borrar la serie'; end if;
  for i in 1..4 loop
    select * into r from public.auth_login_reservar(k, 5, 86400, 900, b + interval '40 seconds' + (i || ' seconds')::interval);
    perform public.auth_login_resolver(k, false, 5, b + interval '40 seconds' + (i || ' seconds')::interval);
    if r.bloqueado_hasta is not null then raise exception 'la serie nueva bloqueó antes del 5.º fallo (%)', i; end if;
  end loop;
  select * into r from public.auth_login_reservar(k, 5, 86400, 900, b + interval '45 seconds');
  if r.bloqueado_hasta is null then raise exception 'cinco fallos nuevos debían bloquear'; end if;
  delete from public.auth_login_intentos;
  -- Antes de 10 s (y a los 10 s exactos) la reserva sigue en vuelo: el login correcto NO borra los fallos de otras peticiones
  perform public.auth_login_reservar(k, 5, 86400, 900, b);
  perform public.auth_login_reservar(k, 5, 86400, 900, b + interval '2 seconds');
  perform public.auth_login_resolver(k, true, 5, b + interval '12 seconds');                -- 10 s exactos tras la última reserva
  select * into f from public.auth_login_intentos where clave = k;
  if f.fallos <> 1 or f.en_vuelo <> 1 then raise exception 'a los 10 s exactos seguía en vuelo (fallos %, en_vuelo %)', f.fallos, f.en_vuelo; end if;
  -- Una reserva resuelta a destiempo (más de 10 s después de la última): la huérfana no cuenta y la serie se borra
  perform public.auth_login_reservar(k, 5, 86400, 900, b + interval '13 seconds');
  perform public.auth_login_resolver(k, true, 5, b + interval '24 seconds');
  select count(*) into n from public.auth_login_intentos where clave = k;
  if n <> 0 then raise exception 'resolver con reservas de hace más de 10 s debía borrar la serie'; end if;
  -- Un fallo resuelto tarde solo baja en_vuelo a 0 y conserva el fallo contado
  perform public.auth_login_reservar(k, 5, 86400, 900, b);
  perform public.auth_login_resolver(k, false, 5, b + interval '60 seconds');
  select * into f from public.auth_login_intentos where clave = k;
  if f.fallos <> 1 or f.en_vuelo <> 0 then raise exception 'resolver(false) tardío: fallos %, en_vuelo %', f.fallos, f.en_vuelo; end if;
  delete from public.auth_login_intentos;

  -- Resolver sin fila no falla; el contador de en_vuelo nunca baja de 0
  perform public.auth_login_resolver('k_inexistente', true, 5, b);
  perform public.auth_login_reservar(k, 5, 86400, 900, b);
  perform public.auth_login_resolver(k, false, 5, b);
  perform public.auth_login_resolver(k, false, 5, b);
  select * into f from public.auth_login_intentos where clave = k;
  if f.en_vuelo <> 0 then raise exception 'en_vuelo no debe ser negativo'; end if;
  -- Reiniciar: borra la serie y desbloquea
  for i in 1..5 loop perform public.auth_login_reservar(k, 5, 86400, 900, b); end loop;
  perform public.auth_login_reiniciar(k);
  select * into r from public.auth_login_reservar(k, 5, 86400, 900, b);
  if not r.permitido or r.bloqueado_hasta is not null then raise exception 'reiniciar debía desbloquear'; end if;
  perform public.auth_login_reiniciar('k_inexistente');
  -- Claves distintas no se mezclan
  perform public.auth_login_reservar('otra', 5, 86400, 900, b);
  select count(*) into n from public.auth_login_intentos;
  if n <> 2 then raise exception 'una clave no debe afectar a otra'; end if;
  -- Sin p_ahora usa now() de la BD
  delete from public.auth_login_intentos;
  perform public.auth_login_reservar(k);
  select count(*) into n from public.auth_login_intentos where clave = k and ventana_inicio = now() and actualizado_en = now();
  if n <> 1 then raise exception 'sin p_ahora debía usar now() de la BD'; end if;
  begin perform public.auth_login_reservar(''); raise exception 'clave vacía aceptada';
  exception when raise_exception then if sqlerrm <> 'clave inválida' then raise; end if; end;
  delete from public.auth_login_intentos;
  raise notice 'OK: login: reservar/resolver/reiniciar, ventana de 24 h, bloqueo de 15 min, 5.ª que acierta';
end $$;

-- 3. Códigos: emitir (60 s, topes, guardado, reemplazo) y verificar (un solo uso, 5 intentos, vigencia, propósito)
do $$
declare b timestamptz := now(); k text := 'k_correo'; r text; c record; i integer; n integer;
begin
  delete from public.auth_codigos; delete from public.auth_limites_eventos;
  -- Marca de purga reciente para que la emisión no purgue los datos sembrados
  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en) values ('purga', 'purga', b);

  r := public.auth_codigo_emitir(k, 'verify', 'h1', 60, 10, 250, 86400, 600, b);
  if r <> 'enviado' then raise exception 'primera emisión: %', r; end if;
  select * into c from public.auth_codigos where clave = k and proposito = 'verify';
  if c.codigo_hmac <> 'h1' or c.intentos <> 0 or c.expira_en <> b + interval '10 minutes' then raise exception 'código mal guardado'; end if;
  select count(*) into n from public.auth_limites_eventos where clave = k and tipo = 'correo' and ocurrido_en = b;
  if n <> 1 then raise exception 'falta el evento del correo'; end if;
  select count(*) into n from public.auth_limites_eventos where clave = 'global' and tipo = 'global' and ocurrido_en = b;
  if n <> 1 then raise exception 'falta el evento global'; end if;
  -- 60 s: reciente no guarda ni cuenta
  r := public.auth_codigo_emitir(k, 'verify', 'h2', 60, 10, 250, 86400, 600, b + interval '59 seconds');
  if r <> 'reciente' then raise exception 'a los 59 s debía ser reciente: %', r; end if;
  select * into c from public.auth_codigos where clave = k and proposito = 'verify';
  if c.codigo_hmac <> 'h1' then raise exception 'reciente no debe reemplazar el código'; end if;
  select count(*) into n from public.auth_limites_eventos where clave = k and tipo = 'correo';
  if n <> 1 then raise exception 'reciente no debe contar'; end if;
  -- Pasados los 60 s se envía y reemplaza al anterior (que deja de servir) con los intentos en 0
  perform public.auth_codigo_verificar(k, 'verify', 'x', 5, b + interval '61 seconds');          -- suma un intento al h1
  r := public.auth_codigo_emitir(k, 'verify', 'h2', 60, 10, 250, 86400, 600, b + interval '61 seconds');
  if r <> 'enviado' then raise exception 'a los 61 s debía enviar: %', r; end if;
  select * into c from public.auth_codigos where clave = k and proposito = 'verify';
  if c.codigo_hmac <> 'h2' or c.intentos <> 0 or c.expira_en <> b + interval '61 seconds' + interval '10 minutes' then raise exception 'el reemplazo no reinició el código'; end if;
  if public.auth_codigo_verificar(k, 'verify', 'h1', 5, b + interval '62 seconds') <> 'incorrecto' then raise exception 'el código anterior debía dejar de servir'; end if;
  -- Un solo uso
  if public.auth_codigo_verificar(k, 'verify', 'h2', 5, b + interval '63 seconds') <> 'ok' then raise exception 'el código vigente debía dar ok'; end if;
  if public.auth_codigo_verificar(k, 'verify', 'h2', 5, b + interval '64 seconds') <> 'invalido' then raise exception 'el código se usó dos veces'; end if;
  select count(*) into n from public.auth_codigos where clave = k;
  if n <> 0 then raise exception 'el código consumido debía borrarse'; end if;
  if public.auth_codigo_verificar('k_sin_codigo', 'verify', 'h2', 5, b) <> 'invalido' then raise exception 'sin código debía ser inválido'; end if;

  -- Verificación y restablecimiento no son intercambiables y conviven (uno por propósito)
  delete from public.auth_codigos; delete from public.auth_limites_eventos where clave <> 'purga';
  perform public.auth_codigo_emitir(k, 'verify', 'hv', 0, 10, 250, 86400, 600, b);
  perform public.auth_codigo_emitir(k, 'reset', 'hr', 0, 10, 250, 86400, 600, b);
  select count(*) into n from public.auth_codigos where clave = k;
  if n <> 2 then raise exception 'debía haber un código por propósito'; end if;
  if public.auth_codigo_verificar(k, 'reset', 'hv', 5, b) <> 'incorrecto' then raise exception 'el código de verificación sirvió para restablecer'; end if;
  if public.auth_codigo_verificar(k, 'verify', 'hr', 5, b) <> 'incorrecto' then raise exception 'el código de restablecimiento sirvió para verificar'; end if;
  if public.auth_codigo_verificar(k, 'verify', 'hv', 5, b) <> 'ok' then raise exception 'verify debía dar ok'; end if;
  if public.auth_codigo_verificar(k, 'reset', 'hr', 5, b) <> 'ok' then raise exception 'reset debía dar ok'; end if;
  begin perform public.auth_codigo_emitir(k, 'otro', 'h', 60, 10, 250, 86400, 600, b); raise exception 'propósito inválido aceptado';
  exception when raise_exception then if sqlerrm <> 'propósito inválido' then raise; end if; end;

  -- 5 intentos: del 1.º al 5.º 'incorrecto'; del 6.º en adelante 'invalido'; ni el correcto lo activa después
  delete from public.auth_codigos; delete from public.auth_limites_eventos where clave <> 'purga';
  perform public.auth_codigo_emitir(k, 'verify', 'h1', 60, 10, 250, 86400, 600, b);
  for i in 1..5 loop
    if public.auth_codigo_verificar(k, 'verify', 'mal' || i, 5, b + (i || ' seconds')::interval) <> 'incorrecto' then raise exception 'intento % debía ser incorrecto', i; end if;
  end loop;
  if public.auth_codigo_verificar(k, 'verify', 'mal6', 5, b + interval '6 seconds') <> 'invalido' then raise exception 'el 6.º intento debía ser inválido'; end if;
  if public.auth_codigo_verificar(k, 'verify', 'h1', 5, b + interval '7 seconds') <> 'invalido' then raise exception 'el código correcto activó tras 5 intentos'; end if;
  -- Vigencia de 10 min
  perform public.auth_codigo_emitir(k, 'verify', 'h3', 60, 10, 250, 86400, 600, b + interval '2 minutes');
  if public.auth_codigo_verificar(k, 'verify', 'h3', 5, b + interval '2 minutes' + interval '599 seconds') <> 'ok' then raise exception 'a los 599 s debía servir'; end if;
  perform public.auth_codigo_emitir(k, 'verify', 'h4', 60, 10, 250, 86400, 600, b + interval '5 minutes');
  if public.auth_codigo_verificar(k, 'verify', 'h4', 5, b + interval '15 minutes') <> 'invalido' then raise exception 'a los 10 min debía vencer'; end if;
  -- Un código señuelo (HMAC que ningún código real produce) no verifica con un valor normal
  perform public.auth_codigo_emitir('k_senuelo', 'verify', 'senuelo_aleatorio_no_adivinable', 60, 10, 250, 86400, 600, b);
  if public.auth_codigo_verificar('k_senuelo', 'verify', 'h1', 5, b) <> 'incorrecto' then raise exception 'el señuelo no debe verificarse'; end if;

  -- Tope por destinatario: 10 en 24 h (separados por 61 s); el 11.º 'limitado' y no toca el código
  delete from public.auth_codigos; delete from public.auth_limites_eventos where clave <> 'purga';
  for i in 1..10 loop
    r := public.auth_codigo_emitir(k, 'verify', 'd' || i, 60, 10, 250, 86400, 600, b + (i * 61 || ' seconds')::interval);
    if r <> 'enviado' then raise exception 'emisión % debía enviarse: %', i, r; end if;
  end loop;
  r := public.auth_codigo_emitir(k, 'verify', 'd11', 60, 10, 250, 86400, 600, b + interval '1000 seconds');
  if r <> 'limitado' then raise exception 'la 11.ª debía ser limitada: %', r; end if;
  select * into c from public.auth_codigos where clave = k and proposito = 'verify';
  if c.codigo_hmac <> 'd10' then raise exception 'limitado no debe reemplazar el código'; end if;
  -- reciente tiene prioridad sobre limitado y a las 24 h del primer evento (b+61 s) el tope libera 1 lugar
  r := public.auth_codigo_emitir(k, 'verify', 'd12', 60, 10, 250, 86400, 600, b + interval '610 seconds' + interval '30 seconds');
  if r <> 'reciente' then raise exception 'debía ser reciente: %', r; end if;
  r := public.auth_codigo_emitir(k, 'verify', 'd12', 60, 10, 250, 86400, 600, b + interval '24 hours' + interval '62 seconds');
  if r <> 'enviado' then raise exception 'pasadas 24 h del primer evento debía enviar: %', r; end if;
  -- Otro destinatario no se ve afectado
  r := public.auth_codigo_emitir('k_otro', 'verify', 'z', 60, 10, 250, 86400, 600, b + interval '1000 seconds');
  if r <> 'enviado' then raise exception 'otro destinatario debía poder recibir: %', r; end if;

  -- Tope global (parámetro 3 para la prueba): cuenta eventos de todos los destinatarios
  delete from public.auth_codigos; delete from public.auth_limites_eventos where clave <> 'purga';
  if public.auth_codigo_emitir('g1', 'verify', 'a', 60, 10, 3, 86400, 600, b) <> 'enviado' then raise exception 'g1'; end if;
  if public.auth_codigo_emitir('g2', 'verify', 'a', 60, 10, 3, 86400, 600, b) <> 'enviado' then raise exception 'g2'; end if;
  if public.auth_codigo_emitir('g3', 'reset', 'a', 60, 10, 3, 86400, 600, b) <> 'enviado' then raise exception 'g3'; end if;
  if public.auth_codigo_emitir('g4', 'verify', 'a', 60, 10, 3, 86400, 600, b) <> 'limitado' then raise exception 'el tope global debía limitar al 4.º'; end if;
  select count(*) into n from public.auth_codigos where clave = 'g4';
  if n <> 0 then raise exception 'limitado global guardó un código'; end if;
  if public.auth_codigo_emitir('g4', 'verify', 'a', 60, 10, 3, 86400, 600, b + interval '24 hours' + interval '1 second') <> 'enviado' then
    raise exception 'pasadas 24 h el tope global debía liberarse';
  end if;
  -- Valores por defecto: 60 s, 10 por destinatario y 250 globales (sin parámetros opcionales)
  delete from public.auth_codigos; delete from public.auth_limites_eventos where clave <> 'purga';
  if public.auth_codigo_emitir('def', 'verify', 'a', 60, 10, 250, 86400, 600, b) <> 'enviado' then raise exception 'def'; end if;
  if public.auth_codigo_emitir('def', 'verify', 'b') <> 'reciente' then raise exception 'los valores por defecto deben dar 60 s con now()'; end if;
  begin perform public.auth_codigo_emitir('', 'verify', 'h'); raise exception 'clave vacía aceptada';
  exception when raise_exception then if sqlerrm <> 'parámetros inválidos' then raise; end if; end;

  -- I-4: la emisión NO purga (la purga es una llamada aparte): ni con la marca vencida ni con filas viejas
  delete from public.auth_codigos; delete from public.auth_limites_eventos;
  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en) values ('purga', 'purga', b - interval '2 days'), ('viejo', 'correo', b - interval '3 days');
  perform public.auth_codigo_emitir('p1', 'verify', 'a', 60, 10, 250, 86400, 600, b);
  select count(*) into n from public.auth_limites_eventos where clave = 'viejo';
  if n <> 1 then raise exception 'la emisión no debe purgar (el evento de 3 días desapareció)'; end if;
  select count(*) into n from public.auth_limites_eventos where clave = 'purga' and ocurrido_en = b - interval '2 days';
  if n <> 1 then raise exception 'la emisión no debe tocar la marca de purga'; end if;
  delete from public.auth_codigos; delete from public.auth_limites_eventos;
  raise notice 'OK: códigos: emitir (60 s, topes, reemplazo, sin purga) y verificar (un solo uso, 5 intentos, vigencia, propósito)';
end $$;

-- 4. Límites por IP (ventana deslizante) y tope de filas
do $$
declare b timestamptz := now(); k text := 'k_ip'; r text; n integer;
begin
  delete from public.auth_limites_eventos;
  -- Límite 3 por 600 s (deslizante): eventos en 0, 300 y 400 s
  if public.auth_limite_registrar(k, 'ip_intento', 3, 600, b) <> 'ok' then raise exception 'ev 1'; end if;
  if public.auth_limite_registrar(k, 'ip_intento', 3, 600, b + interval '300 seconds') <> 'ok' then raise exception 'ev 2'; end if;
  if public.auth_limite_registrar(k, 'ip_intento', 3, 600, b + interval '400 seconds') <> 'ok' then raise exception 'ev 3'; end if;
  if public.auth_limite_registrar(k, 'ip_intento', 3, 600, b + interval '500 seconds') <> 'limitado' then raise exception 'el 4.º debía limitarse'; end if;
  select count(*) into n from public.auth_limites_eventos where clave = k;
  if n <> 3 then raise exception 'limitado no debe insertar (hay %)', n; end if;
  -- A los 601 s ya salió el primero (deslizante, no por bloques): cabe uno; a los 650 s el cupo vuelve a estar lleno
  if public.auth_limite_registrar(k, 'ip_intento', 3, 600, b + interval '601 seconds') <> 'ok' then raise exception 'a 601 s debía caber uno'; end if;
  if public.auth_limite_registrar(k, 'ip_intento', 3, 600, b + interval '650 seconds') <> 'limitado' then raise exception 'a 650 s debía limitarse'; end if;
  -- Otro tipo y otra clave son independientes
  if public.auth_limite_registrar(k, 'ip_pedido', 3, 600, b) <> 'ok' then raise exception 'otro tipo'; end if;
  if public.auth_limite_registrar('k_ip2', 'ip_intento', 3, 600, b) <> 'ok' then raise exception 'otra clave'; end if;
  -- 10 pedidos por hora y 30 intentos por 10 min: los números de INV-010
  delete from public.auth_limites_eventos;
  for n in 1..10 loop
    if public.auth_limite_registrar('hora', 'ip_pedido', 10, 3600, b + (n || ' seconds')::interval) <> 'ok' then raise exception 'pedido % de la hora', n; end if;
  end loop;
  if public.auth_limite_registrar('hora', 'ip_pedido', 10, 3600, b + interval '11 seconds') <> 'limitado' then raise exception 'el pedido 11 debía limitarse'; end if;
  for n in 1..30 loop
    if public.auth_limite_registrar('diez', 'ip_intento', 30, 600, b + (n || ' seconds')::interval) <> 'ok' then raise exception 'intento % de 10 min', n; end if;
  end loop;
  if public.auth_limite_registrar('diez', 'ip_intento', 30, 600, b + interval '31 seconds') <> 'limitado' then raise exception 'el intento 31 debía limitarse'; end if;
  begin perform public.auth_limite_registrar('purga', 'ip_intento', 3, 600, b); raise exception 'la clave purga fue aceptada';
  exception when raise_exception then if sqlerrm <> 'parámetros inválidos' then raise; end if; end;

  -- Tope de 500 000 filas VIGENTES (B-1): las filas vencidas (más de 2 días) no cuentan; las vigentes sí
  delete from public.auth_limites_eventos;
  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en)
    select 'viejo' || g, 'ip_intento', b - interval '3 days' from generate_series(1, 500001) g;
  if public.auth_limite_registrar('nueva0', 'ip_intento', 30, 600, b) <> 'ok' then
    raise exception 'con 500 001 filas de hace 3 días debía registrar (las vencidas no cuentan para el tope)';
  end if;
  select count(*) into n from public.auth_limites_eventos where ocurrido_en < b - interval '2 days';
  if n <> 500001 then raise exception 'lejos del tope no debía purgar (quedan % vencidas)', n; end if;
  -- 499 999 vigentes en total (nueva0 + 499 998): aún cabe; en el tope exacto (500 000) todavía registra; por encima, 'lleno'.
  -- Cerca del tope (450 000 o más vigentes) cada llamada libera un lote de 5 000 filas vencidas sin bloquear
  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en)
    select 'relleno' || g, 'ip_intento', b from generate_series(1, 499998) g;
  if public.auth_limite_registrar('nueva1', 'ip_intento', 30, 600, b) <> 'ok' then raise exception 'con 499 999 vigentes debía registrar'; end if;   -- ahora 500 000
  if public.auth_limite_registrar('nueva2', 'ip_intento', 30, 600, b) <> 'ok' then raise exception 'con 500 000 vigentes aún debía registrar'; end if;   -- ahora 500 001
  if public.auth_limite_registrar('nueva3', 'ip_intento', 30, 600, b) <> 'lleno' then raise exception 'con 500 001 vigentes debía responder lleno'; end if;
  if public.auth_limite_registrar('nueva1', 'ip_intento', 1, 600, b) <> 'limitado' then raise exception 'una clave ya en el límite sigue limitada'; end if;
  select count(*) into n from public.auth_limites_eventos where ocurrido_en < b - interval '2 days';
  if n <> 500001 - 3 * 5000 then raise exception 'cerca del tope cada llamada debía liberar 5 000 vencidas (quedan %)', n; end if;
  select count(*) into n from public.auth_limites_eventos where ocurrido_en >= b - interval '2 days';
  if n <> 500001 then raise exception 'la purga por lotes no debe tocar filas vigentes (hay %)', n; end if;
  -- Recuperación: al vencer las filas vigentes (pasan más de 2 días) la tabla vuelve a aceptar eventos sin esperar a una purga
  if public.auth_limite_registrar('nueva4', 'ip_intento', 30, 600, b + interval '3 days') <> 'ok' then
    raise exception 'pasados 2 días las filas dejan de contar y debía registrar';
  end if;
  delete from public.auth_limites_eventos;
  if public.auth_limite_registrar('nueva3', 'ip_intento', 30, 600, b) <> 'ok' then raise exception 'vaciada la tabla debía registrar'; end if;
  -- El límite por clave sigue usando solo su propia ventana
  delete from public.auth_limites_eventos;
  raise notice 'OK: límites por IP: ventana deslizante, números de INV-010 y tope de 500 000 filas vigentes';
end $$;

-- 5. Baja de cuenta y purga
do $$
declare b timestamptz := now(); r integer; n integer;
begin
  delete from public.auth_login_intentos; delete from public.auth_codigos; delete from public.auth_limites_eventos;
  perform public.auth_login_reservar('cta', 5, 86400, 900, b);
  perform public.auth_login_reservar('otra', 5, 86400, 900, b);
  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en) values ('purga', 'purga', b);
  perform public.auth_codigo_emitir('cta', 'verify', 'h', 60, 10, 250, 86400, 600, b);
  perform public.auth_codigo_emitir('cta', 'reset', 'h', 0, 10, 250, 86400, 600, b);
  perform public.auth_codigo_emitir('otra', 'verify', 'h', 60, 10, 250, 86400, 600, b);
  r := public.auth_borrar_de_cuenta('cta');
  if r <> 3 then raise exception 'la baja borró % filas (esperado 3)', r; end if;
  select count(*) into n from public.auth_login_intentos where clave = 'cta';
  if n <> 0 then raise exception 'quedaron intentos de la cuenta'; end if;
  select count(*) into n from public.auth_codigos where clave = 'cta';
  if n <> 0 then raise exception 'quedaron códigos de la cuenta'; end if;
  select count(*) into n from public.auth_login_intentos where clave = 'otra';
  if n <> 1 then raise exception 'la baja borró intentos de otra cuenta'; end if;
  select count(*) into n from public.auth_codigos where clave = 'otra';
  if n <> 1 then raise exception 'la baja borró códigos de otra cuenta'; end if;
  -- Los eventos de límites NO se borran con la cuenta (no se reinicia el tope diario)
  select count(*) into n from public.auth_limites_eventos where clave = 'cta' and tipo = 'correo';
  if n <> 2 then raise exception 'la baja no debe borrar los eventos de límites (hay %)', n; end if;
  r := public.auth_borrar_de_cuenta('no_existe');
  if r <> 0 then raise exception 'cuenta inexistente: %', r; end if;
  -- El tope de 10/día sigue contando tras la baja y un nuevo registro con el mismo correo
  delete from public.auth_login_intentos; delete from public.auth_codigos; delete from public.auth_limites_eventos;
  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en) values ('purga', 'purga', b);
  for r in 1..10 loop
    insert into public.auth_limites_eventos (clave, tipo, ocurrido_en) values ('baja', 'correo', b - interval '1 hour');
  end loop;
  perform public.auth_borrar_de_cuenta('baja');
  if public.auth_codigo_emitir('baja', 'verify', 'h', 60, 10, 250, 86400, 600, b) <> 'limitado' then raise exception 'la baja reinició el tope diario'; end if;
  delete from public.auth_limites_eventos;

  -- Purga: eventos 2 días; intentos y códigos 30 días; marca 'purga'; una vez al día
  delete from public.auth_login_intentos; delete from public.auth_codigos; delete from public.auth_limites_eventos;
  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en) values
    ('ev3d', 'correo', b - interval '3 days'), ('ev47h', 'correo', b - interval '47 hours'), ('ev1d', 'correo', b - interval '1 day');
  insert into public.auth_login_intentos (clave, fallos, ventana_inicio, actualizado_en) values
    ('in31', 1, b - interval '31 days', b - interval '31 days'), ('in29', 1, b - interval '29 days', b - interval '29 days');
  insert into public.auth_codigos (clave, proposito, codigo_hmac, emitido_en, expira_en) values
    ('co31', 'verify', 'h', b - interval '31 days', b - interval '31 days' + interval '10 minutes'),
    ('co29', 'verify', 'h', b - interval '29 days', b - interval '29 days' + interval '10 minutes');
  r := public.auth_purgar(b);
  if r <> 3 then raise exception 'la purga borró % filas (esperado 3: 1 evento, 1 intento, 1 código)', r; end if;
  select count(*) into n from public.auth_limites_eventos where clave = 'ev3d';
  if n <> 0 then raise exception 'sobrevivió el evento de 3 días'; end if;
  select count(*) into n from public.auth_limites_eventos where clave in ('ev47h', 'ev1d');
  if n <> 2 then raise exception 'la purga borró eventos vigentes'; end if;
  select count(*) into n from public.auth_login_intentos where clave = 'in31';
  if n <> 0 then raise exception 'sobrevivió el intento de 31 días'; end if;
  select count(*) into n from public.auth_login_intentos where clave = 'in29';
  if n <> 1 then raise exception 'la purga borró un intento de 29 días'; end if;
  select count(*) into n from public.auth_codigos where clave = 'co31';
  if n <> 0 then raise exception 'sobrevivió el código de 31 días'; end if;
  select count(*) into n from public.auth_codigos where clave = 'co29';
  if n <> 1 then raise exception 'la purga borró un código de 29 días'; end if;
  select count(*) into n from public.auth_limites_eventos where clave = 'purga' and tipo = 'purga' and ocurrido_en = b;
  if n <> 1 then raise exception 'falta la marca de purga'; end if;
  -- La segunda purga del mismo día no borra nada, ni siquiera lo vencido
  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en) values ('ev5d', 'correo', b - interval '5 days');
  r := public.auth_purgar(b + interval '23 hours');
  if r <> -1 then raise exception 'segunda purga del día devolvió % (esperado -1)', r; end if;
  select count(*) into n from public.auth_limites_eventos where clave = 'ev5d';
  if n <> 1 then raise exception 'la segunda purga del día borró filas'; end if;
  -- Pasado un día vuelve a purgar y la marca se renueva (una sola fila 'purga'; no se cuenta ni se borra a sí misma)
  r := public.auth_purgar(b + interval '25 hours');
  if r < 1 then raise exception 'pasado un día debía purgar (%)', r; end if;
  select count(*) into n from public.auth_limites_eventos where clave = 'ev5d';
  if n <> 0 then raise exception 'la purga siguiente no borró el evento de 5 días'; end if;
  select count(*) into n from public.auth_limites_eventos where clave = 'purga';
  if n <> 1 then raise exception 'debe haber una sola marca de purga (hay %)', n; end if;

  -- Purga por lotes (I-4): p_lote filas por tabla y llamada; con trabajo pendiente la marca NO se renueva
  delete from public.auth_login_intentos; delete from public.auth_codigos; delete from public.auth_limites_eventos;
  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en) select 'lote' || g, 'correo', b - interval '3 days' from generate_series(1, 5) g;
  if public.auth_purgar(b, 2) <> 2 then raise exception 'el primer lote debía borrar 2'; end if;
  select count(*) into n from public.auth_limites_eventos where clave = 'purga';
  if n <> 0 then raise exception 'con trabajo pendiente no debía renovarse la marca'; end if;
  if public.auth_purgar(b, 2) <> 2 then raise exception 'el segundo lote debía borrar 2'; end if;
  if public.auth_purgar(b, 2) <> 1 then raise exception 'el tercer lote debía borrar 1'; end if;      -- 1 < lote: terminó
  select count(*) into n from public.auth_limites_eventos where clave = 'purga';
  if n <> 1 then raise exception 'terminada la purga debía quedar la marca'; end if;
  if public.auth_purgar(b, 2) <> -1 then raise exception 'ya purgado hoy debía devolver -1'; end if;
  begin perform public.auth_purgar(b, 0); raise exception 'lote 0 aceptado';
  exception when raise_exception then if sqlerrm <> 'lote inválido' then raise; end if; end;
  -- (con otra sesión purgando, auth_purgar devuelve -1 sin esperar: se prueba con sesiones reales en probar.sh)
  delete from public.auth_login_intentos; delete from public.auth_codigos; delete from public.auth_limites_eventos;
  raise notice 'OK: baja de cuenta (sin tocar eventos de límites) y purga (2 y 30 días, por lotes, marca, una vez al día)';
end $$;

-- 6. Las funciones también funcionan con el rol del backend (SECURITY INVOKER: necesita los GRANT de tablas y secuencia)
do $$
declare r record; t text;
begin
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    raise notice 'AVISO: no existe el rol service_role en esta base; se omite la prueba con ese rol';
    return;
  end if;
  set local role service_role;
  select * into r from public.auth_login_reservar('k_rol');
  if not r.permitido then raise exception 'service_role no pudo reservar'; end if;
  perform public.auth_login_resolver('k_rol', true);
  perform public.auth_login_reiniciar('k_rol');
  t := public.auth_codigo_emitir('k_rol', 'verify', 'h');
  if t <> 'enviado' then raise exception 'service_role no pudo emitir (%)', t; end if;
  if public.auth_codigo_verificar('k_rol', 'verify', 'h') <> 'ok' then raise exception 'service_role no pudo verificar'; end if;
  if public.auth_limite_registrar('k_rol', 'ip_intento', 5, 600) <> 'ok' then raise exception 'service_role no pudo registrar el límite'; end if;
  perform public.auth_borrar_de_cuenta('k_rol');
  perform public.auth_purgar();
  reset role;
  -- anon y authenticated no pueden ni llamar a las funciones ni leer las tablas
  foreach t in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = t) then
      execute format('set local role %I', t);
      begin
        perform public.auth_login_reservar('k_rol');
        reset role;
        raise exception '% pudo ejecutar auth_login_reservar', t;
      exception when insufficient_privilege then reset role;
      end;
      execute format('set local role %I', t);
      begin
        perform 1 from public.auth_codigos;
        reset role;
        raise exception '% pudo leer auth_codigos', t;
      exception when insufficient_privilege then reset role;
      end;
    end if;
  end loop;
  delete from public.auth_login_intentos; delete from public.auth_codigos; delete from public.auth_limites_eventos;
  raise notice 'OK: service_role usa las funciones; anon y authenticated no';
end $$;
