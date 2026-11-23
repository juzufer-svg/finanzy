-- CHG-013 · INV-028 — Sin duplicados en categorías ni presupuestos
-- Ejecutar en Supabase → SQL Editor DESPUÉS de 2026-11-23_recurrentes.sql y ANTES (o junto con) el despliegue.
-- Es seguro repetirlo.
--
-- 1. Categorías repetidas (misma persona, mismo nombre exacto y mismo tipo): se conserva la más antigua.
--    Sus transacciones, presupuestos y recurrentes pasan a la que se conserva; nada se pierde.
-- 2. Presupuestos repetidos (misma persona, categoría y mes): se conserva el de mayor límite.
-- 3. Se crean las restricciones UNIQUE para que no vuelva a pasar.
-- Todo lo que se borra queda copiado en el esquema privado `respaldo` (sin acceso para anon/authenticated).

create schema if not exists respaldo;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on schema respaldo from anon';
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'revoke all on schema respaldo from authenticated';
  end if;
end $$;

create table if not exists respaldo.duplicados_categorias (like public.categorias);
alter table respaldo.duplicados_categorias add column if not exists conservada_id uuid;
alter table respaldo.duplicados_categorias add column if not exists respaldado_en timestamptz default now();
create table if not exists respaldo.duplicados_presupuestos (like public.presupuestos);
alter table respaldo.duplicados_presupuestos add column if not exists respaldado_en timestamptz default now();

begin;

-- 1) Categorías: mapa duplicada → conservada
create temporary table mapa_categorias on commit drop as
select id as duplicada_id, conservada_id
  from (
    select id,
           first_value(id) over (partition by usuario_id, nombre, tipo order by created_at nulls last, id) as conservada_id
      from public.categorias
  ) t
 where id <> conservada_id;

insert into respaldo.duplicados_categorias
select c.*, m.conservada_id, now()
  from public.categorias c join mapa_categorias m on m.duplicada_id = c.id;

update public.transacciones t set categoria_id = m.conservada_id
  from mapa_categorias m where t.categoria_id = m.duplicada_id;
update public.presupuestos p set categoria_id = m.conservada_id
  from mapa_categorias m where p.categoria_id = m.duplicada_id;
update public.recurrentes r set categoria_id = m.conservada_id
  from mapa_categorias m where r.categoria_id = m.duplicada_id;
delete from public.categorias c using mapa_categorias m where c.id = m.duplicada_id;

-- 2) Presupuestos repetidos (también los que quedaron repetidos al fusionar categorías)
create temporary table presupuestos_sobrantes on commit drop as
select id
  from (
    select id,
           row_number() over (partition by usuario_id, categoria_id, mes_ano order by limite_mensual desc, id) as n
      from public.presupuestos
  ) t
 where n > 1;

insert into respaldo.duplicados_presupuestos
select p.*, now() from public.presupuestos p join presupuestos_sobrantes s on s.id = p.id;
delete from public.presupuestos p using presupuestos_sobrantes s where p.id = s.id;

-- 3) Restricciones
create unique index if not exists categorias_usuario_nombre_tipo_unico
  on public.categorias (usuario_id, nombre, tipo);
create unique index if not exists presupuestos_usuario_categoria_mes_unico
  on public.presupuestos (usuario_id, categoria_id, mes_ano);

commit;

-- Comprobación: dos índices únicos, y cuántas filas se respaldaron (0 si no había duplicados)
select indexname from pg_indexes
 where schemaname = 'public' and indexname in ('categorias_usuario_nombre_tipo_unico', 'presupuestos_usuario_categoria_mes_unico');
select (select count(*) from respaldo.duplicados_categorias) as categorias_fusionadas,
       (select count(*) from respaldo.duplicados_presupuestos) as presupuestos_quitados;
