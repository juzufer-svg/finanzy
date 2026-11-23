-- CHG-013 · INV-028: después de 2026-11-23_sin_duplicados.sql (ejecutado dos veces)
do $$
declare n bigint; u uuid := '66666666-6666-6666-6666-666666666666'; keep uuid := 'dddddddd-0000-0000-0000-000000000002';  -- la que tenía más transacciones
begin
  select count(*) into n from public.categorias where usuario_id = u; if n <> 2 then raise exception 'categorías: % (esperado 2: Comida gasto + Comida ingreso)', n; end if;
  select count(*) into n from public.transacciones where usuario_id = u and categoria_id = keep; if n <> 3 then raise exception 'transacciones no movidas: %', n; end if;
  select count(*) into n from public.recurrentes where usuario_id = u and categoria_id = keep; if n <> 1 then raise exception 'recurrente no movida'; end if;
  select count(*) into n from public.presupuestos where usuario_id = u; if n <> 2 then raise exception 'presupuestos: % (esperado 2)', n; end if;
  select limite_mensual into n from public.presupuestos where usuario_id = u and mes_ano = '2026-11'; if n <> 300 then raise exception 'se conservó el límite equivocado: %', n; end if;
  select count(*) into n from respaldo.duplicados_categorias; if n <> 1 then raise exception 'respaldo categorías: %', n; end if;
  select count(*) into n from respaldo.duplicados_presupuestos; if n <> 1 then raise exception 'respaldo presupuestos: %', n; end if;
  begin
    insert into public.categorias(usuario_id, nombre, tipo) values (u, 'Comida', 'gasto');
    raise exception 'se pudo duplicar una categoría';
  exception when unique_violation then null;
  end;
  begin
    insert into public.presupuestos(usuario_id, categoria_id, limite_mensual, mes_ano) values (u, keep, 1, '2026-11');
    raise exception 'se pudo duplicar un presupuesto';
  exception when unique_violation then null;
  end;
  raise notice 'OK: duplicados fusionados con respaldo y restricciones activas';
end $$;
