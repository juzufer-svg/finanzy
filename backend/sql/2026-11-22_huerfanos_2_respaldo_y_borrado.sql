-- CHG-005 · BL-015 — Registros huérfanos: PASO 2 de 3 (RESPALDO + BORRADO)
-- Ejecutar en Supabase → SQL Editor DESPUÉS de revisar el paso 1.
-- Aprobado por el dueño el 2026-11-22.
--
-- Qué hace, todo en una sola transacción (si algo falla, no cambia nada):
--   a) Copia los huérfanos al esquema privado "respaldo" (no se publica por la API de Supabase).
--   b) Borra los huérfanos de categorias, transacciones, presupuestos y metas.
--   c) Deja "Sin categoría" los movimientos de usuarios reales que apuntaban a una categoría
--      huérfana o inexistente, y borra los presupuestos de usuarios reales en esa situación
--      (es lo mismo que harán las llaves foráneas del paso 3). Ambos quedan anotados en "respaldo".
-- Es seguro repetirlo: la segunda vez no encuentra nada que copiar ni borrar.
-- Al final muestra cuántas filas quedaron en el respaldo. Para descargarlas, mira el bloque
-- "DESCARGAR EL RESPALDO" al final del archivo.

begin;

create schema if not exists respaldo;
revoke all on schema respaldo from public;
do $$
begin
  -- En Supabase existen estos roles; en otra base puede que no.
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on schema respaldo from anon';
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'revoke all on schema respaldo from authenticated';
  end if;
end $$;

-- Tablas de respaldo con la misma forma que las originales + fecha del respaldo
create table if not exists respaldo.huerfanos_categorias    (like public.categorias);
create table if not exists respaldo.huerfanos_transacciones (like public.transacciones);
create table if not exists respaldo.huerfanos_presupuestos  (like public.presupuestos);
create table if not exists respaldo.huerfanos_metas         (like public.metas);
alter table respaldo.huerfanos_categorias    add column if not exists respaldado_en timestamptz default now();
alter table respaldo.huerfanos_transacciones add column if not exists respaldado_en timestamptz default now();
alter table respaldo.huerfanos_presupuestos  add column if not exists respaldado_en timestamptz default now();
alter table respaldo.huerfanos_metas         add column if not exists respaldado_en timestamptz default now();
create table if not exists respaldo.presupuestos_sin_categoria (like public.presupuestos);
alter table respaldo.presupuestos_sin_categoria add column if not exists respaldado_en timestamptz default now();

-- Si las tablas originales ganaron columnas después del primer respaldo (p. ej. medio_pago),
-- se agregan también al respaldo para poder repetir este script sin errores.
do $$
declare par record; col record;
begin
  for par in select * from (values
      ('categorias', 'huerfanos_categorias'), ('transacciones', 'huerfanos_transacciones'),
      ('presupuestos', 'huerfanos_presupuestos'), ('metas', 'huerfanos_metas'),
      ('presupuestos', 'presupuestos_sin_categoria')) v(origen, destino) loop
    for col in select a.attname, format_type(a.atttypid, a.atttypmod) as tipo
                 from pg_attribute a
                where a.attrelid = format('public.%I', par.origen)::regclass and a.attnum > 0 and not a.attisdropped loop
      execute format('alter table respaldo.%I add column if not exists %I %s', par.destino, col.attname, col.tipo);
    end loop;
  end loop;
end $$;

-- a) Respaldo (sin duplicar si se repite)
insert into respaldo.huerfanos_transacciones
select (jsonb_populate_record(null::respaldo.huerfanos_transacciones, to_jsonb(t) || jsonb_build_object('respaldado_en', now()))).*
  from public.transacciones t
 where not exists (select 1 from public.users u where u.id = t.usuario_id)
   and not exists (select 1 from respaldo.huerfanos_transacciones r where r.id = t.id);

insert into respaldo.huerfanos_presupuestos
select (jsonb_populate_record(null::respaldo.huerfanos_presupuestos, to_jsonb(p) || jsonb_build_object('respaldado_en', now()))).*
  from public.presupuestos p
 where not exists (select 1 from public.users u where u.id = p.usuario_id)
   and not exists (select 1 from respaldo.huerfanos_presupuestos r where r.id = p.id);

insert into respaldo.huerfanos_metas
select (jsonb_populate_record(null::respaldo.huerfanos_metas, to_jsonb(m) || jsonb_build_object('respaldado_en', now()))).*
  from public.metas m
 where not exists (select 1 from public.users u where u.id = m.usuario_id)
   and not exists (select 1 from respaldo.huerfanos_metas r where r.id = m.id);

insert into respaldo.huerfanos_categorias
select (jsonb_populate_record(null::respaldo.huerfanos_categorias, to_jsonb(c) || jsonb_build_object('respaldado_en', now()))).*
  from public.categorias c
 where not exists (select 1 from public.users u where u.id = c.usuario_id)
   and not exists (select 1 from respaldo.huerfanos_categorias r where r.id = c.id);

-- b) Borrado de huérfanos que dependen de categorías
delete from public.transacciones t where not exists (select 1 from public.users u where u.id = t.usuario_id);
delete from public.presupuestos  p where not exists (select 1 from public.users u where u.id = p.usuario_id);
delete from public.metas         m where not exists (select 1 from public.users u where u.id = m.usuario_id);

-- c) Referencias de usuarios reales a categorías huérfanas o inexistentes (normalmente 0 filas;
--    ver la consulta 2 del paso 1). Antes de cambiarlas se anota qué categoría tenían.
create table if not exists respaldo.categoria_quitada (
  transaccion_id uuid, categoria_id_anterior uuid, respaldado_en timestamptz default now());

insert into respaldo.categoria_quitada (transaccion_id, categoria_id_anterior)
select t.id, t.categoria_id from public.transacciones t
 where t.categoria_id is not null
   and not exists (select 1 from public.categorias c
                    where c.id = t.categoria_id
                      and exists (select 1 from public.users u where u.id = c.usuario_id));
update public.transacciones t set categoria_id = null
 where t.categoria_id is not null
   and not exists (select 1 from public.categorias c
                    where c.id = t.categoria_id
                      and exists (select 1 from public.users u where u.id = c.usuario_id));

insert into respaldo.presupuestos_sin_categoria
select (jsonb_populate_record(null::respaldo.presupuestos_sin_categoria, to_jsonb(p) || jsonb_build_object('respaldado_en', now()))).*
  from public.presupuestos p
 where not exists (select 1 from public.categorias c
                    where c.id = p.categoria_id
                      and exists (select 1 from public.users u where u.id = c.usuario_id));
delete from public.presupuestos p
 where not exists (select 1 from public.categorias c
                    where c.id = p.categoria_id
                      and exists (select 1 from public.users u where u.id = c.usuario_id));

-- d) Por último, las categorías huérfanas
delete from public.categorias c where not exists (select 1 from public.users u where u.id = c.usuario_id);

commit;

-- Comprobación: el respaldo debe tener los huérfanos del paso 1, y en public ya no debe quedar ninguno.
select 'respaldo.categorias' as tabla, count(*) as filas from respaldo.huerfanos_categorias
union all select 'respaldo.transacciones', count(*) from respaldo.huerfanos_transacciones
union all select 'respaldo.presupuestos',  count(*) from respaldo.huerfanos_presupuestos
union all select 'respaldo.metas',         count(*) from respaldo.huerfanos_metas
union all select 'movimientos tuyos que quedaron sin categoría', count(*) from respaldo.categoria_quitada
union all select 'presupuestos tuyos borrados (categoría inexistente)', count(*) from respaldo.presupuestos_sin_categoria
union all select 'quedan huérfanos en public', (
    (select count(*) from public.categorias    c where not exists (select 1 from public.users u where u.id = c.usuario_id))
  + (select count(*) from public.transacciones t where not exists (select 1 from public.users u where u.id = t.usuario_id))
  + (select count(*) from public.presupuestos  p where not exists (select 1 from public.users u where u.id = p.usuario_id))
  + (select count(*) from public.metas         m where not exists (select 1 from public.users u where u.id = m.usuario_id)));

-- ===================== DESCARGAR EL RESPALDO (opcional, recomendado) =====================
-- Ejecuta cada consulta por separado y usa el botón "Export" → "Download CSV" del resultado:
--   select * from respaldo.huerfanos_categorias;
--   select * from respaldo.huerfanos_transacciones;
--   select * from respaldo.huerfanos_presupuestos;
--   select * from respaldo.huerfanos_metas;
--   select * from respaldo.categoria_quitada;
--   select * from respaldo.presupuestos_sin_categoria;
--
-- ===================== DESHACER (solo si hiciera falta) =====================
-- Los registros quedan guardados en el esquema "respaldo" y en tus CSV. Como apuntan a usuarios
-- que ya no existen, después del paso 3 PostgreSQL no permitirá devolverlos a las tablas
-- (justamente eso es lo que se quiere evitar). Si necesitas recuperar algo, pídele ayuda a Claude.
