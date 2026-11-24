-- CHG-020 · ADR-010 · INV-037 a INV-041 — Estado de autenticación persistente (bloqueos de login, códigos y límites de envío)
-- Ejecutar en Supabase → SQL Editor ANTES de desplegar el backend que lo usa (sin estas tablas el login respondería 503).
-- No toca datos existentes. Es seguro repetirlo (idempotente). Puede pegarse COMPLETO: no usa tablas temporales entre
-- sentencias ni meta-comandos de psql.
--
-- Privacidad (INV-040): el correo y la IP llegan aquí SOLO como huella HMAC (la calcula el backend con una clave derivada
-- de SECRET_KEY, que no está en la BD) y los códigos SOLO como HMAC. Esta migración nunca recibe ni guarda correos, IP ni
-- códigos en claro.
-- Reloj (INV-038): todas las ventanas usan now() de la BD. El parámetro p_ahora existe SOLO para las pruebas SQL; el
-- backend nunca lo envía.
-- Atomicidad (INV-038): cada función bloquea la fila (FOR UPDATE) o la clave (pg_advisory_xact_lock) antes de decidir.
-- Orden de bloqueos en la emisión de códigos: primero la clave del correo, luego la global (evita interbloqueos).

-- ---------------------------------------------------------------------------------------------------------------------
-- Tablas
-- ---------------------------------------------------------------------------------------------------------------------

-- Serie de fallos de login por correo (clave = huella HMAC del correo)
create table if not exists public.auth_login_intentos (
  clave varchar(128) primary key,
  fallos integer not null default 0,
  en_vuelo integer not null default 0,                       -- reservas que aún comprueban la contraseña
  ventana_inicio timestamptz not null default now(),         -- primer fallo de la serie (caduca a las 24 h)
  bloqueado_hasta timestamptz,
  actualizado_en timestamptz not null default now(),
  constraint auth_login_intentos_fallos_ck check (fallos >= 0),
  constraint auth_login_intentos_en_vuelo_ck check (en_vuelo >= 0)
);

-- Un código vigente por correo y propósito (INV-007): solo su HMAC
create table if not exists public.auth_codigos (
  clave varchar(128) not null,                               -- huella HMAC del correo
  proposito varchar(10) not null,
  codigo_hmac varchar(128) not null,
  emitido_en timestamptz not null default now(),
  expira_en timestamptz not null,
  intentos integer not null default 0,
  constraint auth_codigos_pk primary key (clave, proposito),
  constraint auth_codigos_proposito_ck check (proposito in ('verify', 'reset')),
  constraint auth_codigos_intentos_ck check (intentos >= 0)
);

-- Eventos de límites (ventanas deslizantes): solo huella, tipo y hora. La fila clave = 'purga' es la marca de última purga.
create table if not exists public.auth_limites_eventos (
  id bigint generated always as identity primary key,
  clave varchar(128) not null,
  tipo varchar(40) not null,
  ocurrido_en timestamptz not null default now()
);
create index if not exists auth_limites_eventos_clave_idx on public.auth_limites_eventos (clave, tipo, ocurrido_en);
create index if not exists auth_limites_eventos_ocurrido_idx on public.auth_limites_eventos (ocurrido_en);
create index if not exists auth_login_intentos_actualizado_idx on public.auth_login_intentos (actualizado_en);
create index if not exists auth_codigos_emitido_idx on public.auth_codigos (emitido_en);

-- ---------------------------------------------------------------------------------------------------------------------
-- Purga oportunista (como mucho una vez al día entre todas las instancias; sin tarea programada)
-- Retención: eventos de límites 2 días; intentos de login y códigos 30 días. Devuelve cuántas filas borró, o -1 si no
-- purgó (ya se purgó hace menos de un día o la está haciendo otra sesión).
-- ---------------------------------------------------------------------------------------------------------------------
create or replace function public.auth_purgar(p_ahora timestamptz default now())
returns integer
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_marca timestamptz;
  v_total integer := 0;
  v_n integer;
begin
  select max(e.ocurrido_en) into v_marca from public.auth_limites_eventos e where e.clave = 'purga';
  if v_marca is not null and v_marca > p_ahora - interval '1 day' then
    return -1;
  end if;
  -- Solo una sesión purga; las demás no esperan (no se serializa la emisión de códigos)
  if not pg_try_advisory_xact_lock(hashtextextended('auth_purgar', 0)) then
    return -1;
  end if;
  -- Otra sesión pudo confirmar la marca entre la primera lectura y el bloqueo
  select max(e.ocurrido_en) into v_marca from public.auth_limites_eventos e where e.clave = 'purga';
  if v_marca is not null and v_marca > p_ahora - interval '1 day' then
    return -1;
  end if;

  delete from public.auth_limites_eventos e where e.clave = 'purga';
  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en) values ('purga', 'purga', p_ahora);

  delete from public.auth_limites_eventos e where e.clave <> 'purga' and e.ocurrido_en < p_ahora - interval '2 days';
  get diagnostics v_n = row_count;
  v_total := v_total + v_n;
  delete from public.auth_login_intentos i where i.actualizado_en < p_ahora - interval '30 days';
  get diagnostics v_n = row_count;
  v_total := v_total + v_n;
  delete from public.auth_codigos c where c.emitido_en < p_ahora - interval '30 days';
  get diagnostics v_n = row_count;
  v_total := v_total + v_n;
  return v_total;
end $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- Login: reservar el intento ANTES de comprobar la contraseña y resolverlo después
-- ---------------------------------------------------------------------------------------------------------------------

-- Reserva un intento. permitido = false si el correo está bloqueado (no cuenta). La serie caduca a las 24 h del primer
-- fallo (o cuando venció el bloqueo) y entonces empieza de cero. El 5.º fallo fija el bloqueo de 15 min.
create or replace function public.auth_login_reservar(
  p_clave text,
  p_max integer default 5,
  p_ventana_seg integer default 86400,
  p_bloqueo_seg integer default 900,
  p_ahora timestamptz default now())
returns table (permitido boolean, bloqueado_hasta timestamptz)
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
#variable_conflict use_column
declare
  f public.auth_login_intentos%rowtype;
begin
  if p_clave is null or p_clave = '' then
    raise exception 'clave inválida';
  end if;
  insert into public.auth_login_intentos (clave, ventana_inicio, actualizado_en)
  values (p_clave, p_ahora, p_ahora)
  on conflict (clave) do nothing;
  select * into f from public.auth_login_intentos t where t.clave = p_clave for update;

  if f.bloqueado_hasta is not null and f.bloqueado_hasta > p_ahora then
    return query select false, f.bloqueado_hasta;
    return;
  end if;
  if f.bloqueado_hasta is not null                                                  -- el bloqueo ya venció
     or f.fallos = 0
     or f.ventana_inicio + make_interval(secs => p_ventana_seg) <= p_ahora then      -- pasaron 24 h desde el primer fallo
    f.fallos := 0;
    f.en_vuelo := 0;
    f.ventana_inicio := p_ahora;
    f.bloqueado_hasta := null;
  end if;

  f.fallos := f.fallos + 1;
  f.en_vuelo := f.en_vuelo + 1;
  if f.fallos >= p_max then
    f.bloqueado_hasta := p_ahora + make_interval(secs => p_bloqueo_seg);
  end if;
  update public.auth_login_intentos t
     set fallos = f.fallos, en_vuelo = f.en_vuelo, ventana_inicio = f.ventana_inicio,
         bloqueado_hasta = f.bloqueado_hasta, actualizado_en = p_ahora
   where t.clave = p_clave;
  return query select true, f.bloqueado_hasta;
end $$;

-- Cierra la reserva después de comprobar la contraseña. Si fue incorrecta, el fallo ya estaba contado. Si fue correcta,
-- devuelve el intento (fallos - 1, levanta el bloqueo si quedan menos de p_max) y borra la serie SOLO si ya no hay
-- reservas en vuelo (nunca borra los fallos de peticiones que aún comprueban su contraseña).
create or replace function public.auth_login_resolver(
  p_clave text,
  p_acierto boolean,
  p_max integer default 5,
  p_ahora timestamptz default now())
returns void
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
#variable_conflict use_column
declare
  f public.auth_login_intentos%rowtype;
begin
  select * into f from public.auth_login_intentos t where t.clave = p_clave for update;
  if not found then
    return;
  end if;
  f.en_vuelo := greatest(f.en_vuelo - 1, 0);
  if coalesce(p_acierto, false) then
    f.fallos := greatest(f.fallos - 1, 0);
    if f.fallos < p_max then
      f.bloqueado_hasta := null;
    end if;
    if f.en_vuelo = 0 then
      delete from public.auth_login_intentos t where t.clave = p_clave;
      return;
    end if;
  end if;
  update public.auth_login_intentos t
     set fallos = f.fallos, en_vuelo = f.en_vuelo, bloqueado_hasta = f.bloqueado_hasta, actualizado_en = p_ahora
   where t.clave = p_clave;
end $$;

-- Borra la serie sin condiciones (restablecimiento de contraseña y cambio de contraseña del perfil con éxito)
create or replace function public.auth_login_reiniciar(p_clave text)
returns void
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
  delete from public.auth_login_intentos t where t.clave = p_clave;
end $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- Códigos de correo
-- ---------------------------------------------------------------------------------------------------------------------

-- Emisión en UNA sola transacción: 60 s entre códigos al mismo correo, topes por destinatario y global, registro de los
-- eventos y guardado del HMAC del código (reemplaza al anterior del mismo propósito).
-- Devuelve 'enviado' | 'reciente' | 'limitado'. Con p_espacio_seg <= 0 no se comprueba el espacio (solo para pruebas).
create or replace function public.auth_codigo_emitir(
  p_clave_correo text,
  p_proposito text,
  p_codigo_hmac text,
  p_espacio_seg integer default 60,
  p_limite_destinatario integer default 10,
  p_limite_global integer default 250,
  p_ventana_seg integer default 86400,
  p_vigencia_seg integer default 600,
  p_ahora timestamptz default now())
returns text
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_n integer;
begin
  if p_clave_correo is null or p_clave_correo = '' or p_codigo_hmac is null or p_codigo_hmac = '' then
    raise exception 'parámetros inválidos';
  end if;
  if p_proposito not in ('verify', 'reset') then
    raise exception 'propósito inválido';
  end if;

  perform public.auth_purgar(p_ahora);                       -- oportunista; no espera a otras sesiones

  -- Primero el correo, luego el global (siempre en este orden)
  perform pg_advisory_xact_lock(hashtextextended('auth_emitir:correo:' || p_clave_correo, 0));
  perform pg_advisory_xact_lock(hashtextextended('auth_emitir:global', 0));

  if p_espacio_seg > 0 and exists (
       select 1 from public.auth_limites_eventos e
        where e.clave = p_clave_correo and e.tipo = 'correo'
          and e.ocurrido_en > p_ahora - make_interval(secs => p_espacio_seg)) then
    return 'reciente';
  end if;

  select count(*) into v_n from public.auth_limites_eventos e
   where e.clave = p_clave_correo and e.tipo = 'correo'
     and e.ocurrido_en > p_ahora - make_interval(secs => p_ventana_seg);
  if v_n >= p_limite_destinatario then
    return 'limitado';
  end if;
  select count(*) into v_n from public.auth_limites_eventos e
   where e.clave = 'global' and e.tipo = 'global'
     and e.ocurrido_en > p_ahora - make_interval(secs => p_ventana_seg);
  if v_n >= p_limite_global then
    return 'limitado';
  end if;

  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en) values (p_clave_correo, 'correo', p_ahora);
  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en) values ('global', 'global', p_ahora);
  insert into public.auth_codigos as c (clave, proposito, codigo_hmac, emitido_en, expira_en, intentos)
  values (p_clave_correo, p_proposito, p_codigo_hmac, p_ahora, p_ahora + make_interval(secs => p_vigencia_seg), 0)
  on conflict (clave, proposito) do update
     set codigo_hmac = excluded.codigo_hmac, emitido_en = excluded.emitido_en,
         expira_en = excluded.expira_en, intentos = 0;
  return 'enviado';
end $$;

-- Verifica un código con la fila bloqueada. Devuelve 'ok' (y lo consume: un solo uso), 'incorrecto' (suma un intento;
-- al 5.º lo invalida) o 'invalido' (no existe, venció o ya agotó sus intentos).
create or replace function public.auth_codigo_verificar(
  p_clave_correo text,
  p_proposito text,
  p_codigo_hmac text,
  p_max integer default 5,
  p_ahora timestamptz default now())
returns text
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  c public.auth_codigos%rowtype;
begin
  select * into c from public.auth_codigos t
   where t.clave = p_clave_correo and t.proposito = p_proposito for update;
  if not found then
    return 'invalido';
  end if;
  if c.expira_en <= p_ahora then
    delete from public.auth_codigos t where t.clave = p_clave_correo and t.proposito = p_proposito;
    return 'invalido';
  end if;
  if c.intentos >= p_max then
    return 'invalido';
  end if;
  if p_codigo_hmac is not null and c.codigo_hmac = p_codigo_hmac then
    delete from public.auth_codigos t where t.clave = p_clave_correo and t.proposito = p_proposito;
    return 'ok';
  end if;
  update public.auth_codigos t set intentos = t.intentos + 1
   where t.clave = p_clave_correo and t.proposito = p_proposito;
  return 'incorrecto';
end $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- Límites por IP (ventana deslizante exacta) y baja de cuenta
-- ---------------------------------------------------------------------------------------------------------------------

-- Cuenta los eventos de la clave dentro de la ventana y solo inserta uno si no se llegó al límite.
-- Devuelve 'ok' | 'limitado' | 'lleno' (la tabla supera 500 000 filas: tope contra IP falsificadas, INV-040).
create or replace function public.auth_limite_registrar(
  p_clave text,
  p_tipo text,
  p_limite integer,
  p_ventana_seg integer,
  p_ahora timestamptz default now())
returns text
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_n integer;
begin
  if p_clave is null or p_clave = '' or p_clave = 'purga' or p_tipo is null or p_tipo = '' then
    raise exception 'parámetros inválidos';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('auth_limite:' || p_clave || ':' || p_tipo, 0));
  select count(*) into v_n from public.auth_limites_eventos e
   where e.clave = p_clave and e.tipo = p_tipo
     and e.ocurrido_en > p_ahora - make_interval(secs => p_ventana_seg);
  if v_n >= p_limite then
    return 'limitado';
  end if;
  select count(*) into v_n from (
    select 1 from public.auth_limites_eventos e where e.clave <> 'purga' limit 500001) s;
  if v_n > 500000 then
    return 'lleno';
  end if;
  insert into public.auth_limites_eventos (clave, tipo, ocurrido_en) values (p_clave, p_tipo, p_ahora);
  return 'ok';
end $$;

-- Baja de cuenta: borra intentos y códigos del correo. NO borra los eventos de límites (borrarlos permitiría reiniciar el
-- tope de 10 correos/día registrando de nuevo el mismo correo); esos expiran con la purga (2 días). Devuelve filas borradas.
create or replace function public.auth_borrar_de_cuenta(p_clave_correo text)
returns integer
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_total integer := 0;
  v_n integer;
begin
  delete from public.auth_login_intentos t where t.clave = p_clave_correo;
  get diagnostics v_n = row_count;
  v_total := v_total + v_n;
  delete from public.auth_codigos t where t.clave = p_clave_correo;
  get diagnostics v_n = row_count;
  v_total := v_total + v_n;
  return v_total;
end $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- Permisos: solo el backend (service_role). RLS activada SIN políticas; anon y authenticated no tienen acceso.
-- ---------------------------------------------------------------------------------------------------------------------
do $$
declare
  r record;
  t text;
begin
  alter table public.auth_login_intentos enable row level security;
  alter table public.auth_codigos enable row level security;
  alter table public.auth_limites_eventos enable row level security;

  foreach t in array array['auth_login_intentos', 'auth_codigos', 'auth_limites_eventos'] loop
    execute format('revoke all on public.%I from public', t);
    if exists (select 1 from pg_roles where rolname = 'anon') then
      execute format('revoke all on public.%I from anon', t);
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
      execute format('revoke all on public.%I from authenticated', t);
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
      execute format('grant all on public.%I to service_role', t);
    end if;
  end loop;

  for r in
    select p.oid::regprocedure as f
      from pg_proc p join pg_namespace s on s.oid = p.pronamespace
     where s.nspname = 'public'
       and p.proname in ('auth_login_reservar', 'auth_login_resolver', 'auth_login_reiniciar', 'auth_codigo_emitir',
                         'auth_codigo_verificar', 'auth_limite_registrar', 'auth_borrar_de_cuenta', 'auth_purgar')
  loop
    execute format('revoke all on function %s from public', r.f);
    if exists (select 1 from pg_roles where rolname = 'anon') then
      execute format('revoke all on function %s from anon', r.f);
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
      execute format('revoke all on function %s from authenticated', r.f);
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
      execute format('grant execute on function %s to service_role', r.f);
    end if;
  end loop;
end $$;

-- Comprobación: 3 filas con rowsecurity = true
select tablename, rowsecurity from pg_tables
 where schemaname = 'public' and tablename in ('auth_login_intentos', 'auth_codigos', 'auth_limites_eventos')
 order by tablename;
