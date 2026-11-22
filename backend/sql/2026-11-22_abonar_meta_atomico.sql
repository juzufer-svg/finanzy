-- CHG-004 · INV-008 — Abono a una meta en una sola transacción de PostgreSQL
-- Ejecutar en Supabase → SQL Editor. Se puede ejecutar antes o después de desplegar el backend:
-- mientras la función no exista, el backend usa el método anterior (no se rompe nada).
-- Es segura de repetir (CREATE OR REPLACE). No modifica ni borra datos existentes.
--
-- Qué garantiza:
--   * La meta se bloquea (FOR UPDATE) mientras se suma: dos abonos simultáneos no se pisan.
--   * La transacción de gasto y la suma a la meta se guardan juntas o no se guarda ninguna.
--   * Solo actúa si la meta pertenece al usuario indicado (INV-001).
--   * Solo la puede ejecutar el backend (rol service_role); el navegador no puede llamarla.

create or replace function public.abonar_meta(
  p_meta_id     uuid,
  p_usuario_id  uuid,
  p_monto       numeric,
  p_fecha       date,
  p_descripcion text default 'Abono a meta de ahorro'
)
returns setof public.metas
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_categoria_id uuid;
begin
  if p_monto is null or p_monto <= 0 or p_monto > 1000000000000 then
    raise exception 'monto_invalido' using errcode = '22023';
  end if;

  -- Bloquea la meta del usuario hasta terminar (evita sumas perdidas)
  perform 1 from public.metas
   where id = p_meta_id and usuario_id = p_usuario_id
   for update;
  if not found then
    raise exception 'meta_no_encontrada' using errcode = 'P0002';
  end if;

  -- Categoría especial «Ahorro» del usuario (se crea si no existe). El bloqueo por usuario evita
  -- crear dos «Ahorro» si llegan a la vez abonos a metas distintas.
  perform pg_advisory_xact_lock(hashtext('finanzy_ahorro:' || p_usuario_id::text));
  select id into v_categoria_id
    from public.categorias
   where usuario_id = p_usuario_id and nombre = 'Ahorro'
   limit 1;
  if v_categoria_id is null then
    insert into public.categorias (id, usuario_id, nombre, icono, tipo)
    values (gen_random_uuid(), p_usuario_id, 'Ahorro', '🐷', 'gasto')
    returning id into v_categoria_id;
  end if;

  insert into public.transacciones (id, usuario_id, categoria_id, monto, descripcion, fecha, tipo)
  values (gen_random_uuid(), p_usuario_id, v_categoria_id, p_monto,
          coalesce(nullif(left(p_descripcion, 255), ''), 'Abono a meta de ahorro'), p_fecha, 'gasto');

  return query
    update public.metas
       set monto_actual = coalesce(monto_actual, 0) + p_monto
     where id = p_meta_id and usuario_id = p_usuario_id
     returning *;
end;
$$;

-- Por defecto PostgreSQL deja ejecutar funciones a todos: se restringe al backend.
-- NUNCA dar EXECUTE a anon/authenticated: recibe el usuario como parámetro y permitiría suplantarlo.
revoke all on function public.abonar_meta(uuid, uuid, numeric, date, text) from public, anon, authenticated;
grant execute on function public.abonar_meta(uuid, uuid, numeric, date, text) to service_role;

-- Comprobación: debe mostrar  existe = true, backend = true, navegador_anon = false, navegador_auth = false
select to_regprocedure('public.abonar_meta(uuid, uuid, numeric, date, text)') is not null as existe,
       has_function_privilege('service_role',  'public.abonar_meta(uuid, uuid, numeric, date, text)', 'execute') as backend,
       has_function_privilege('anon',          'public.abonar_meta(uuid, uuid, numeric, date, text)', 'execute') as navegador_anon,
       has_function_privilege('authenticated', 'public.abonar_meta(uuid, uuid, numeric, date, text)', 'execute') as navegador_auth;
