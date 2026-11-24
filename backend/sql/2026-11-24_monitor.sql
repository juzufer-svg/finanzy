-- CHG-017 · INV-036 — Monitor de consumos: contadores diarios propios (solo agregados, sin datos personales)
-- Ejecutar en Supabase → SQL Editor ANTES de desplegar el backend que lo usa. No toca datos existentes.
-- Es seguro repetirlo (idempotente). Puede pegarse completo: no usa tablas temporales entre sentencias.

-- Consumo agregado por día UTC. No pertenece a ningún usuario: jamás guarda correos, teléfonos, textos ni ids de usuario.
create table if not exists public.contadores_diarios (
  fecha date not null,
  metrica varchar(40) not null,
  origen varchar(20) not null default 'general',
  cantidad bigint not null default 0,
  constraint contadores_diarios_pk primary key (fecha, metrica, origen),   -- clave única: fecha + métrica + origen
  constraint contadores_diarios_metrica_ck check (metrica in (
    'claude_llamadas', 'claude_tokens_entrada', 'claude_tokens_salida',
    'brevo_correos_enviados', 'whatsapp_enviados', 'whatsapp_recibidos', 'purga')),
  constraint contadores_diarios_origen_ck check (origen in ('asistente', 'whatsapp', 'general')),
  constraint contadores_diarios_cantidad_ck check (cantidad >= 0)
);

-- Incremento atómico: varias escrituras simultáneas no pierden cuenta (el backend lo invoca por RPC)
create or replace function public.incrementar_contador(p_fecha date, p_metrica text, p_origen text, p_cantidad bigint)
returns bigint
language plpgsql
set search_path = public
as $$
declare total bigint;
begin
  if p_cantidad is null or p_cantidad < 0 then
    raise exception 'cantidad inválida';
  end if;
  insert into public.contadores_diarios as c (fecha, metrica, origen, cantidad)
  values (p_fecha, p_metrica, coalesce(p_origen, 'general'), p_cantidad)
  on conflict (fecha, metrica, origen) do update set cantidad = c.cantidad + excluded.cantidad
  returning c.cantidad into total;
  return total;
end $$;

-- Purga oportunista (una vez al día, también con varias instancias): solo quien logra insertar la marca
-- (fecha, 'purga', 'general') borra las filas con fecha < hoy - 90 días. Devuelve cuántas filas borró, o -1 si
-- otra instancia ya purgó hoy.
create or replace function public.purgar_contadores(p_hoy date)
returns integer
language plpgsql
set search_path = public
as $$
declare insertadas integer; borradas integer;
begin
  insert into public.contadores_diarios (fecha, metrica, origen, cantidad)
  values (p_hoy, 'purga', 'general', 0)
  on conflict (fecha, metrica, origen) do nothing;
  get diagnostics insertadas = row_count;
  if insertadas = 0 then
    return -1;
  end if;
  delete from public.contadores_diarios where fecha < p_hoy - 90;
  get diagnostics borradas = row_count;
  return borradas;
end $$;

-- Solo el backend (service_role) usa la tabla y las funciones; anon y authenticated no tienen acceso
do $$
begin
  alter table public.contadores_diarios enable row level security;   -- sin políticas: nadie más entra
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on public.contadores_diarios from anon;
    revoke all on function public.incrementar_contador(date, text, text, bigint) from anon;
    revoke all on function public.purgar_contadores(date) from anon;
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    revoke all on public.contadores_diarios from authenticated;
    revoke all on function public.incrementar_contador(date, text, text, bigint) from authenticated;
    revoke all on function public.purgar_contadores(date) from authenticated;
  end if;
  revoke all on function public.incrementar_contador(date, text, text, bigint) from public;
  revoke all on function public.purgar_contadores(date) from public;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant all on public.contadores_diarios to service_role;
    grant execute on function public.incrementar_contador(date, text, text, bigint) to service_role;
    grant execute on function public.purgar_contadores(date) to service_role;
  end if;
end $$;

-- Comprobación: 1 fila con rowsecurity = true
select tablename, rowsecurity from pg_tables where schemaname = 'public' and tablename = 'contadores_diarios';
