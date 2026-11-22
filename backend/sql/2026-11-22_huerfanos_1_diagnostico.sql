-- CHG-005 · BL-015 — Registros huérfanos: PASO 1 de 3 (DIAGNÓSTICO, solo lectura)
-- Ejecutar en Supabase → SQL Editor. No cambia nada: solo cuenta y muestra.
--
-- Un registro "huérfano" apunta a un usuario que ya no existe (o a ninguno). Aparecen
-- porque en la base real faltan las llaves foráneas con ON DELETE CASCADE.
-- Conteo esperado según la revisión anterior: categorías 53, transacciones 9,
-- presupuestos 1, metas 1 (total 64). Si los números son muy distintos, NO sigas con
-- el paso 2 y avísale a Claude.

-- 1) Huérfanos por tabla (usuario inexistente o vacío)
select 'categorias' as tabla, count(*) as huerfanos
  from public.categorias c where not exists (select 1 from public.users u where u.id = c.usuario_id)
union all
select 'transacciones', count(*)
  from public.transacciones t where not exists (select 1 from public.users u where u.id = t.usuario_id)
union all
select 'presupuestos', count(*)
  from public.presupuestos p where not exists (select 1 from public.users u where u.id = p.usuario_id)
union all
select 'metas', count(*)
  from public.metas m where not exists (select 1 from public.users u where u.id = m.usuario_id);

-- 2) Efecto colateral sobre usuarios que SÍ existen (debería dar 0 en ambas filas).
--    Si da más de 0, son movimientos o presupuestos tuyos que usan una categoría huérfana:
--    el paso 2 deja esos movimientos "Sin categoría" y borra esos presupuestos.
select 'transacciones de usuarios reales con categoría huérfana o inexistente' as revision, count(*) as filas
  from public.transacciones t
 where t.categoria_id is not null
   and exists (select 1 from public.users u where u.id = t.usuario_id)
   and not exists (select 1 from public.categorias c
                    where c.id = t.categoria_id
                      and exists (select 1 from public.users u2 where u2.id = c.usuario_id))
union all
select 'presupuestos de usuarios reales con categoría huérfana o inexistente', count(*)
  from public.presupuestos p
 where exists (select 1 from public.users u where u.id = p.usuario_id)
   and not exists (select 1 from public.categorias c
                    where c.id = p.categoria_id
                      and exists (select 1 from public.users u2 where u2.id = c.usuario_id));

-- 3) Llaves foráneas que existen hoy (para comparar con el paso 3).
--    Lo correcto: usuario_id → users ON DELETE CASCADE en las 4 tablas,
--    transacciones.categoria_id → SET NULL y presupuestos.categoria_id → CASCADE.
select con.conrelid::regclass as tabla,
       att.attname           as columna,
       con.confrelid::regclass as referencia,
       case con.confdeltype when 'c' then 'CASCADE' when 'n' then 'SET NULL'
            when 'a' then 'NO ACTION' when 'r' then 'RESTRICT' else con.confdeltype::text end as al_borrar,
       con.conname as nombre
  from pg_constraint con
  join pg_attribute att on att.attrelid = con.conrelid and att.attnum = con.conkey[1]
 where con.contype = 'f'
   and con.conrelid in ('public.categorias'::regclass, 'public.transacciones'::regclass,
                        'public.presupuestos'::regclass, 'public.metas'::regclass)
 order by 1, 2;
