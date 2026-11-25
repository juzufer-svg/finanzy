-- CHG-023 · INV-053 a INV-062 · ADR-012 — Panel de administración de usuarios (solo el Dueño)
-- Ejecutar en Supabase → SQL Editor ANTES de desplegar el backend que lo usa (sin la columna `suspendida`,
-- `get_session_version` fallaría y todas las sesiones darían 503). Puede pegarse COMPLETO. Es seguro repetirlo (idempotente).
-- No cambia ninguna fila existente de `users`: `suspendida` empieza en false y `ultimo_acceso` en nula.
-- Las funciones devuelven `jsonb` con claves EXPLÍCITAS (nunca `select *` ni `to_jsonb(users)`) y solo conteos del uso:
-- nada de contraseñas, importes ni textos de otros usuarios. Todas son SECURITY INVOKER y solo `service_role` las ejecuta.
-- Nota: `users.created_at` es TIMESTAMP sin zona y guarda UTC; aquí se interpreta como UTC y se devuelve con «Z».

-- 1. Columnas nuevas en users
alter table public.users add column if not exists suspendida boolean not null default false;
alter table public.users add column if not exists ultimo_acceso timestamptz;

-- 2. Registro de acciones del administrador: SIN llave foránea (sobrevive a la baja) y sin datos personales
create table if not exists public.auditoria_admin (
  id bigint generated always as identity primary key,
  creado_en timestamptz not null default now(),
  accion text not null,
  usuario_id uuid not null,
  constraint auditoria_admin_accion_ck check (accion in ('suspender', 'reactivar', 'cerrar_sesiones', 'eliminar'))
);
create index if not exists idx_auditoria_admin_creado on public.auditoria_admin (creado_en desc, id desc);

-- 3. Auxiliar: registra una acción y aplica la retención (365 días) y el tope (10 000 filas) SOLO cuando se superan.
-- La limpieza usa un bloqueo «try» (nunca espera a otra sesión que ya limpia). Corre en la transacción de la acción:
-- si falla, la acción se revierte (no hay acción sin registro).
create or replace function public.admin_registrar_auditoria(p_accion text, p_usuario_id uuid)
returns void
language plpgsql
set search_path = public
as $$
begin
  insert into public.auditoria_admin (accion, usuario_id) values (p_accion, p_usuario_id);
  if exists (select 1 from public.auditoria_admin where creado_en < now() - interval '365 days')
     or (select count(*) from (select 1 from public.auditoria_admin limit 10001) t) > 10000 then
    if pg_try_advisory_xact_lock(hashtextextended('admin_auditoria_limpieza', 0)) then
      delete from public.auditoria_admin where creado_en < now() - interval '365 days';
      delete from public.auditoria_admin where id in (
        select id from public.auditoria_admin order by creado_en desc, id desc offset 10000);
    end if;
  end if;
end $$;

-- 4. Listado paginado con búsqueda LITERAL (se escapan \ % _) por correo o nombre, sin distinguir mayúsculas.
-- Devuelve {total, usuarios:[...]}; los conteos se calculan solo para las filas de la página (25 como máximo).
create or replace function public.admin_listar_usuarios(p_q text, p_limite integer, p_desplazamiento integer)
returns jsonb
language plpgsql
stable
set search_path = public
as $$
declare
  v_q text := nullif(btrim(coalesce(p_q, '')), '');
  v_lim integer := least(greatest(coalesce(p_limite, 25), 1), 25);
  v_desp integer := least(greatest(coalesce(p_desplazamiento, 0), 0), 9975);
  v_esc text := chr(92);
  v_patron text;
  v_total bigint;
  v_usuarios jsonb;
begin
  if v_q is not null then
    if char_length(v_q) > 60 then
      raise exception 'búsqueda demasiado larga';
    end if;
    v_patron := '%' || replace(replace(replace(v_q, v_esc, v_esc || v_esc), '%', v_esc || '%'), '_', v_esc || '_') || '%';
  end if;

  select count(*) into v_total from public.users u
   where v_patron is null
      or u.email ilike v_patron escape v_esc
      or coalesce(u.full_name, '') ilike v_patron escape v_esc;

  select coalesce(jsonb_agg(jsonb_build_object(
           'id', p.id,
           'correo', p.email,
           'nombre', p.full_name,
           'estado', case when p.suspendida then 'suspendida' when coalesce(p.is_active, false) then 'activa' else 'pendiente' end,
           'moneda', p.currency,
           'registrado_en', to_char(p.created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
           'ultimo_acceso', to_char(p.ultimo_acceso at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
           'uso', jsonb_build_object(
             'transacciones', (select count(*) from public.transacciones t where t.usuario_id = p.id))
         ) order by p.rn), '[]'::jsonb)
    into v_usuarios
    from (
      select u.id, u.email, u.full_name, u.currency, u.is_active, u.suspendida, u.created_at, u.ultimo_acceso,
             row_number() over (order by u.created_at desc nulls last, u.id) as rn
        from public.users u
       where v_patron is null
          or u.email ilike v_patron escape v_esc
          or coalesce(u.full_name, '') ilike v_patron escape v_esc
       order by u.created_at desc nulls last, u.id
       limit v_lim offset v_desp
    ) p;

  return jsonb_build_object(
    'generado_en', to_char(now() at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    'total', v_total,
    'usuarios', v_usuarios);
end $$;

-- 5. Detalle de un usuario (null si no existe): datos básicos y SOLO conteos de uso
create or replace function public.admin_detalle_usuario(p_id uuid)
returns jsonb
language plpgsql
stable
set search_path = public
as $$
declare r jsonb;
begin
  select jsonb_build_object(
           'id', u.id,
           'correo', u.email,
           'nombre', u.full_name,
           'estado', case when u.suspendida then 'suspendida' when coalesce(u.is_active, false) then 'activa' else 'pendiente' end,
           'moneda', u.currency,
           'registrado_en', to_char(u.created_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
           'ultimo_acceso', to_char(u.ultimo_acceso at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
           'uso', jsonb_build_object(
             'transacciones', (select count(*) from public.transacciones t where t.usuario_id = u.id),
             'categorias', (select count(*) from public.categorias c where c.usuario_id = u.id),
             'presupuestos', (select count(*) from public.presupuestos b where b.usuario_id = u.id),
             'metas', (select count(*) from public.metas m where m.usuario_id = u.id),
             'recurrentes', (select count(*) from public.recurrentes e where e.usuario_id = u.id),
             'whatsapp_conectado', exists (select 1 from public.whatsapp_enlaces w where w.usuario_id = u.id)))
    into r
    from public.users u
   where u.id = p_id;
  return r;
end $$;

-- 6. Suspender: UNA transacción con la fila bloqueada. Devuelve ok | no_existe | ya | pendiente
create or replace function public.admin_suspender_usuario(p_id uuid)
returns text
language plpgsql
set search_path = public
as $$
declare v_susp boolean; v_activa boolean;
begin
  select u.suspendida, coalesce(u.is_active, false) into v_susp, v_activa
    from public.users u where u.id = p_id for update;
  if not found then return 'no_existe'; end if;
  if v_susp then return 'ya'; end if;
  if not v_activa then return 'pendiente'; end if;
  update public.users set suspendida = true, session_version = session_version + 1 where id = p_id;
  delete from public.whatsapp_enlaces where usuario_id = p_id;
  perform public.admin_registrar_auditoria('suspender', p_id);
  return 'ok';
end $$;

-- 7. Reactivar: solo quita la marca (las sesiones viejas no reviven: su versión ya no coincide). ok | no_existe | no_suspendida
create or replace function public.admin_reactivar_usuario(p_id uuid)
returns text
language plpgsql
set search_path = public
as $$
declare v_susp boolean;
begin
  select u.suspendida into v_susp from public.users u where u.id = p_id for update;
  if not found then return 'no_existe'; end if;
  if not v_susp then return 'no_suspendida'; end if;
  update public.users set suspendida = false where id = p_id;
  perform public.admin_registrar_auditoria('reactivar', p_id);
  return 'ok';
end $$;

-- 8. Cerrar sesiones: sube la versión en exactamente 1 y desconecta WhatsApp. ok | no_existe
create or replace function public.admin_cerrar_sesiones_usuario(p_id uuid)
returns text
language plpgsql
set search_path = public
as $$
declare v_id uuid;
begin
  select u.id into v_id from public.users u where u.id = p_id for update;
  if not found then return 'no_existe'; end if;
  update public.users set session_version = session_version + 1 where id = p_id;
  delete from public.whatsapp_enlaces where usuario_id = p_id;
  perform public.admin_registrar_auditoria('cerrar_sesiones', p_id);
  return 'ok';
end $$;

-- 9. Eliminar: auditoría + borrado con cascada en la misma transacción. ok | no_existe | correo_distinto
create or replace function public.admin_eliminar_usuario(p_id uuid, p_correo text)
returns text
language plpgsql
set search_path = public
as $$
declare v_correo text;
begin
  select u.email into v_correo from public.users u where u.id = p_id for update;
  if not found then return 'no_existe'; end if;
  if lower(btrim(coalesce(p_correo, ''))) is distinct from lower(btrim(coalesce(v_correo, ''))) then
    return 'correo_distinto';
  end if;
  perform public.admin_registrar_auditoria('eliminar', p_id);
  delete from public.users where id = p_id;
  return 'ok';
end $$;

-- 10. Registro de acciones (paginado, más reciente primero). El correo se une al leer y solo si la cuenta aún existe.
create or replace function public.admin_auditoria(p_limite integer, p_desplazamiento integer)
returns jsonb
language plpgsql
stable
set search_path = public
as $$
declare
  v_lim integer := least(greatest(coalesce(p_limite, 25), 1), 25);
  v_desp integer := least(greatest(coalesce(p_desplazamiento, 0), 0), 9975);
  v_total bigint; v_registros jsonb;
begin
  select count(*) into v_total from public.auditoria_admin;
  select coalesce(jsonb_agg(jsonb_build_object(
           'id', r.id,
           'fecha', to_char(r.creado_en at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
           'accion', r.accion,
           'usuario_id', r.usuario_id,
           'usuario_correo', r.correo
         ) order by r.rn), '[]'::jsonb)
    into v_registros
    from (
      select a.id, a.creado_en, a.accion, a.usuario_id, u.email as correo,
             row_number() over (order by a.creado_en desc, a.id desc) as rn
        from public.auditoria_admin a
        left join public.users u on u.id = a.usuario_id
       order by a.creado_en desc, a.id desc
       limit v_lim offset v_desp
    ) r;
  return jsonb_build_object(
    'generado_en', to_char(now() at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    'total', v_total,
    'registros', v_registros);
end $$;

-- 11. Último acceso: UNA sentencia condicional con el reloj de la BD (como mucho una escritura por hora y usuario,
-- aunque lleguen muchos inicios de sesión a la vez). Devuelve true si escribió.
create or replace function public.registrar_acceso(p_id uuid)
returns boolean
language plpgsql
set search_path = public
as $$
declare n integer;
begin
  update public.users set ultimo_acceso = now()
   where id = p_id and (ultimo_acceso is null or ultimo_acceso < now() - interval '1 hour');
  get diagnostics n = row_count;
  return n > 0;
end $$;

-- 12. Solo el backend (service_role) usa la tabla y las funciones; anon, authenticated y public no tienen acceso
do $$
declare f text;
  funciones text[] := array[
    'public.admin_registrar_auditoria(text,uuid)',
    'public.admin_listar_usuarios(text,integer,integer)',
    'public.admin_detalle_usuario(uuid)',
    'public.admin_suspender_usuario(uuid)',
    'public.admin_reactivar_usuario(uuid)',
    'public.admin_cerrar_sesiones_usuario(uuid)',
    'public.admin_eliminar_usuario(uuid,text)',
    'public.admin_auditoria(integer,integer)',
    'public.registrar_acceso(uuid)'];
begin
  alter table public.auditoria_admin enable row level security;   -- sin políticas: nadie más entra
  revoke all on public.auditoria_admin from public;
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on public.auditoria_admin from anon;
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    revoke all on public.auditoria_admin from authenticated;
  end if;
  foreach f in array funciones loop
    execute format('revoke all on function %s from public', f);
    if exists (select 1 from pg_roles where rolname = 'anon') then
      execute format('revoke all on function %s from anon', f);
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
      execute format('revoke all on function %s from authenticated', f);
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
      execute format('grant execute on function %s to service_role', f);
    end if;
  end loop;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant all on public.auditoria_admin to service_role;
  end if;
end $$;

-- Comprobación: auditoria_admin con rowsecurity = true; 2 columnas nuevas en users; 9 funciones
select tablename, rowsecurity from pg_tables where schemaname = 'public' and tablename = 'auditoria_admin';
select column_name, data_type, column_default, is_nullable from information_schema.columns
 where table_schema = 'public' and table_name = 'users' and column_name in ('suspendida', 'ultimo_acceso') order by column_name;
select count(*) as funciones_admin from pg_proc p join pg_namespace s on s.oid = p.pronamespace
 where s.nspname = 'public' and (p.proname like 'admin\_%' or p.proname = 'registrar_acceso');
