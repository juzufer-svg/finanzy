-- Se ejecuta después de los pasos 2 y 3 (dos veces cada uno). Falla con error si algo no cuadra.
do $$
declare n bigint;
begin
  select count(*) into n from respaldo.huerfanos_categorias;    if n <> 53 then raise exception 'respaldo categorias: % (esperado 53)', n; end if;
  select count(*) into n from respaldo.huerfanos_transacciones; if n <> 9  then raise exception 'respaldo transacciones: % (esperado 9)', n; end if;
  select count(*) into n from respaldo.huerfanos_presupuestos;  if n <> 1  then raise exception 'respaldo presupuestos: % (esperado 1)', n; end if;
  select count(*) into n from respaldo.huerfanos_metas;         if n <> 1  then raise exception 'respaldo metas: % (esperado 1)', n; end if;
  select count(*) into n from respaldo.categoria_quitada;       if n <> 1  then raise exception 'categoria_quitada: % (esperado 1)', n; end if;

  -- Los datos del usuario real siguen ahí
  select count(*) into n from public.transacciones; if n <> 2 then raise exception 'transacciones reales: % (esperado 2)', n; end if;
  select count(*) into n from public.categorias;    if n <> 1 then raise exception 'categorias reales: % (esperado 1)', n; end if;
  select count(*) into n from public.presupuestos;  if n <> 1 then raise exception 'presupuestos reales: % (esperado 1)', n; end if;
  select count(*) into n from public.metas;         if n <> 1 then raise exception 'metas reales: % (esperado 1)', n; end if;

  -- Las 6 llaves con la regla correcta y sin duplicados
  select count(*) into n from pg_constraint where contype = 'f'
     and conrelid in ('public.categorias'::regclass, 'public.transacciones'::regclass,
                      'public.presupuestos'::regclass, 'public.metas'::regclass);
  if n <> 6 then raise exception 'llaves foráneas: % (esperado 6)', n; end if;

  -- Borrar una categoría deja sus movimientos sin categoría y borra su presupuesto
  delete from public.categorias where id = 'aaaaaaaa-0000-0000-0000-000000000001';
  select count(*) into n from public.transacciones where categoria_id is not null; if n <> 0 then raise exception 'SET NULL no aplicado'; end if;
  select count(*) into n from public.presupuestos; if n <> 0 then raise exception 'CASCADE de categoría no aplicado'; end if;

  -- Borrar el usuario borra todo lo suyo
  delete from public.users;
  select (select count(*) from public.categorias) + (select count(*) from public.transacciones)
       + (select count(*) from public.presupuestos) + (select count(*) from public.metas) into n;
  if n <> 0 then raise exception 'CASCADE de usuario no aplicado: quedan % filas', n; end if;

  -- Ya no se pueden crear huérfanos
  begin
    insert into public.categorias(usuario_id, nombre, tipo) values ('33333333-3333-3333-3333-333333333333', 'x', 'gasto');
    raise exception 'se pudo insertar una categoría huérfana';
  exception when foreign_key_violation then null;
  end;
  raise notice 'OK: migraciones de huérfanos verificadas';
end $$;
