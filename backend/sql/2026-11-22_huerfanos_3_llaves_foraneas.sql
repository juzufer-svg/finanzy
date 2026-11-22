-- CHG-005 · BL-015 — Registros huérfanos: PASO 3 de 3 (LLAVES FORÁNEAS)
-- Ejecutar en Supabase → SQL Editor DESPUÉS del paso 2.
--
-- Crea (o corrige) las llaves foráneas que impiden que vuelvan a aparecer huérfanos:
--   categorias.usuario_id     → users(id)      ON DELETE CASCADE
--   transacciones.usuario_id  → users(id)      ON DELETE CASCADE
--   presupuestos.usuario_id   → users(id)      ON DELETE CASCADE
--   metas.usuario_id          → users(id)      ON DELETE CASCADE
--   transacciones.categoria_id → categorias(id) ON DELETE SET NULL  (el movimiento queda "Sin categoría")
--   presupuestos.categoria_id  → categorias(id) ON DELETE CASCADE   (el presupuesto de esa categoría se borra)
-- Con esto, "Eliminar cuenta" (UC-010) borra de verdad todos los datos del usuario.
--
-- Es seguro repetirlo. Si una llave ya existe con la regla correcta, la deja igual.
-- Si existe con otra regla, la reemplaza. Si quedara algún huérfano, falla con un error
-- claro y no cambia nada (vuelve a correr el paso 2).

begin;

do $$
declare
  r record;
  existente record;
  regla_char "char";
  nombre text;
  huerfanos bigint;
begin
  for r in
    select * from (values
      ('categorias',    'usuario_id',   'users',      'CASCADE'),
      ('transacciones', 'usuario_id',   'users',      'CASCADE'),
      ('presupuestos',  'usuario_id',   'users',      'CASCADE'),
      ('metas',         'usuario_id',   'users',      'CASCADE'),
      ('transacciones', 'categoria_id', 'categorias', 'SET NULL'),
      ('presupuestos',  'categoria_id', 'categorias', 'CASCADE')
    ) as v(tabla, columna, ref, regla)
  loop
    regla_char := case r.regla when 'CASCADE' then 'c' else 'n' end;
    nombre := format('fk_%s_%s', r.tabla, r.columna);

    -- 1) Comprobar que no quedan referencias rotas
    execute format(
      'select count(*) from public.%I t where t.%I is not null and not exists (select 1 from public.%I x where x.id = t.%I)',
      r.tabla, r.columna, r.ref, r.columna) into huerfanos;
    if huerfanos > 0 then
      raise exception 'public.%.% tiene % filas que apuntan a % inexistentes. Ejecuta primero el paso 2.',
        r.tabla, r.columna, huerfanos, r.ref;
    end if;

    -- 2) Quitar llaves de esa columna con una regla distinta
    for existente in
      select con.conname, con.confdeltype, con.confrelid
        from pg_constraint con
        join pg_attribute att on att.attrelid = con.conrelid and att.attnum = con.conkey[1]
       where con.contype = 'f'
         and con.conrelid = format('public.%I', r.tabla)::regclass
         and array_length(con.conkey, 1) = 1
         and att.attname = r.columna
    loop
      if existente.confdeltype <> regla_char or existente.confrelid <> format('public.%I', r.ref)::regclass then
        execute format('alter table public.%I drop constraint %I', r.tabla, existente.conname);
        raise notice 'Reemplazada %.% (%): tenía otra regla', r.tabla, r.columna, existente.conname;
      end if;
    end loop;

    -- 3) Crear la llave si no hay una correcta
    if not exists (
      select 1
        from pg_constraint con
        join pg_attribute att on att.attrelid = con.conrelid and att.attnum = con.conkey[1]
       where con.contype = 'f'
         and con.conrelid = format('public.%I', r.tabla)::regclass
         and att.attname = r.columna
    ) then
      execute format('alter table public.%I add constraint %I foreign key (%I) references public.%I(id) on delete %s',
        r.tabla, nombre, r.columna, r.ref, r.regla);
      raise notice 'Creada % (% → %, on delete %)', nombre, r.columna, r.ref, r.regla;
    end if;
  end loop;
end $$;

-- Índices para que los borrados en cascada sean rápidos (no cambian datos)
create index if not exists idx_transacciones_categoria on public.transacciones(categoria_id);
create index if not exists idx_presupuestos_categoria  on public.presupuestos(categoria_id);

commit;

-- Comprobación: deben salir 6 filas con la regla indicada arriba
select con.conrelid::regclass as tabla, att.attname as columna, con.confrelid::regclass as referencia,
       case con.confdeltype when 'c' then 'CASCADE' when 'n' then 'SET NULL' else con.confdeltype::text end as al_borrar
  from pg_constraint con
  join pg_attribute att on att.attrelid = con.conrelid and att.attnum = con.conkey[1]
 where con.contype = 'f'
   and con.conrelid in ('public.categorias'::regclass, 'public.transacciones'::regclass,
                        'public.presupuestos'::regclass, 'public.metas'::regclass)
 order by 1, 2;
