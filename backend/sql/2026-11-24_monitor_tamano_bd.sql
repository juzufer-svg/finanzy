-- CHG-017 — Monitor de consumos: tamaño de la base de datos de Supabase
-- Ejecutar en Supabase → SQL Editor (después de 2026-11-24_monitor.sql). No toca datos existentes.
-- Es seguro repetirlo (idempotente). Puede pegarse completo.

-- Solo lectura: devuelve el tamaño de la base actual en bytes. No expone datos de nadie.
create or replace function public.tamano_bd()
returns bigint
language sql
stable
security invoker
set search_path = public
as $$
  select pg_database_size(current_database());
$$;

-- Solo el backend (service_role) puede llamarla; anon y authenticated no
do $$
begin
  revoke all on function public.tamano_bd() from public;
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on function public.tamano_bd() from anon;
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    revoke all on function public.tamano_bd() from authenticated;
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant execute on function public.tamano_bd() to service_role;
  end if;
end $$;

-- Comprobación: devuelve un número mayor que 0 (bytes)
select public.tamano_bd() as tamano_bd_bytes;
