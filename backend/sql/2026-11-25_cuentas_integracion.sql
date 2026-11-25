-- CHG-025 (fase c de CHG-019) · INV-008, INV-025, INV-026, INV-046 a INV-052 · ADR-009 puntos 11-13
-- Integración de las cuentas con metas y recurrentes.
-- Ejecutar en Supabase → SQL Editor DESPUÉS de 2026-11-25_cuentas.sql y 2026-11-25_transferencias.sql y ANTES de
-- desplegar el backend de la fase (c). Puede pegarse COMPLETO. Es seguro repetirlo (idempotente) y no toca filas existentes.
--
-- Qué hace:
--  1. `recurrentes.cuenta_id` (opcional): llave compuesta (cuenta_id, usuario_id) → cuentas(id, usuario_id) NO ACTION
--     (la BD impide usar la cuenta de otro usuario; borrar una cuenta con recurrentes asignadas da 23503 → se archiva).
--  2. `abonar_meta` con `p_cuenta_id uuid default null`. Se ELIMINA la firma anterior (5 parámetros) para no crear
--     ambigüedad. Con cuenta, el gasto se inserta con cuenta_id y los disparadores fz001_ pueden abortar TODO con
--     FZ001/FZ002 (ni la meta cambia). Sin cuenta, el comportamiento es idéntico al anterior.
--  3. `confirmar_recurrente(...)`: confirmar una ocurrencia en UNA transacción (bloquea, compara, inserta, avanza).
--     Si algo falla, la fecha NO avanza. Solo la puede ejecutar el backend (service_role).

-- 1. cuenta_id en recurrentes (opcional) con llave compuesta
alter table public.recurrentes add column if not exists cuenta_id uuid;
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'recurrentes_cuenta_fk' and conrelid = 'public.recurrentes'::regclass) then
    alter table public.recurrentes add constraint recurrentes_cuenta_fk
      foreign key (cuenta_id, usuario_id) references public.cuentas (id, usuario_id) on delete no action;
  end if;
end $$;
-- Se recrea (no «if not exists») para que una definición antigua con el mismo nombre no se quede sin avisar.
-- Sirve a la comprobación de la llave foránea al intentar borrar una cuenta.
drop index if exists public.idx_recurrentes_cuenta;
create index idx_recurrentes_cuenta on public.recurrentes (cuenta_id) where cuenta_id is not null;

-- 2. Abono a una meta, con cuenta de origen opcional
drop function if exists public.abonar_meta(uuid, uuid, numeric, date, text);
create or replace function public.abonar_meta(
  p_meta_id     uuid,
  p_usuario_id  uuid,
  p_monto       numeric,
  p_fecha       date,
  p_descripcion text default 'Abono a meta de ahorro',
  p_cuenta_id   uuid default null
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

  -- Con cuenta: los disparadores fz001_ abortan con FZ001 (saldo) o FZ002 (archivada) y NO cambia nada, ni la meta;
  -- una cuenta ajena la rechaza la llave foránea compuesta (23503).
  insert into public.transacciones (id, usuario_id, categoria_id, monto, descripcion, fecha, tipo, cuenta_id)
  values (gen_random_uuid(), p_usuario_id, v_categoria_id, p_monto,
          coalesce(nullif(left(p_descripcion, 255), ''), 'Abono a meta de ahorro'), p_fecha, 'gasto', p_cuenta_id);

  return query
    update public.metas
       set monto_actual = coalesce(monto_actual, 0) + p_monto
     where id = p_meta_id and usuario_id = p_usuario_id
     returning *;
end;
$$;

-- 3. Confirmar una ocurrencia de una recurrente en UNA transacción (ADR-009 punto 13)
--   p_ocurrencia: la fecha que la persona vio como pendiente (compare-and-set contra proxima_fecha)
--   p_siguiente:  la fecha siguiente de la serie (calculada en Python con recurrencia.py, INV-026)
--   p_monto/p_fecha: valores ajustados (null = monto de la plantilla / fecha de la ocurrencia)
--   p_cuenta_indicada: true = usar p_cuenta_id (puede ser null = sin cuenta); false = usar la cuenta de la plantilla
-- Errores: 22023 monto_invalido · P0002 recurrente_no_encontrada · P0001 ocurrencia_cambiada (pausada o ya movida)
--          · FZ001/FZ002 de los disparadores de saldo · 23503 cuenta ajena. En todos, la fecha NO avanza.
drop function if exists public.confirmar_recurrente(uuid, uuid, date, date, numeric, date, uuid, boolean);
create function public.confirmar_recurrente(
  p_usuario_id       uuid,
  p_recurrente_id    uuid,
  p_ocurrencia       date,
  p_siguiente        date,
  p_monto            numeric,
  p_fecha            date,
  p_cuenta_id        uuid,
  p_cuenta_indicada  boolean
)
returns setof public.transacciones
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  r public.recurrentes%rowtype;
  v_cuenta uuid;
  v_monto numeric;
begin
  if p_ocurrencia is null or p_siguiente is null or p_siguiente <= p_ocurrencia then
    raise exception 'fecha_invalida' using errcode = '22023';
  end if;
  if p_monto is not null and (p_monto <= 0 or p_monto > 9999999999.99) then
    raise exception 'monto_invalido' using errcode = '22023';
  end if;

  -- Bloquea la recurrente del usuario hasta terminar: dos confirmaciones simultáneas hacen cola y la 2.ª ve la fecha ya movida
  select * into r from public.recurrentes
   where id = p_recurrente_id and usuario_id = p_usuario_id
   for update;
  if not found then
    raise exception 'recurrente_no_encontrada' using errcode = 'P0002';
  end if;
  if not r.activa or r.proxima_fecha is distinct from p_ocurrencia then
    raise exception 'ocurrencia_cambiada';
  end if;

  v_cuenta := case when coalesce(p_cuenta_indicada, false) then p_cuenta_id else r.cuenta_id end;
  v_monto := coalesce(p_monto, r.monto);

  -- Los disparadores fz001_ pueden abortarlo todo con FZ001/FZ002: entonces la fecha no se ha movido
  return query
    insert into public.transacciones (id, usuario_id, categoria_id, monto, descripcion, fecha, tipo, medio_pago, cuenta_id)
    values (gen_random_uuid(), p_usuario_id, r.categoria_id, v_monto, coalesce(r.descripcion, ''),
            coalesce(p_fecha, p_ocurrencia), r.tipo, r.medio_pago, v_cuenta)
    returning *;

  update public.recurrentes set proxima_fecha = p_siguiente
   where id = p_recurrente_id and usuario_id = p_usuario_id;
end;
$$;

-- 4. Solo el backend (service_role) las ejecuta. NUNCA dar EXECUTE a anon/authenticated: reciben el usuario como parámetro.
revoke all on function public.abonar_meta(uuid, uuid, numeric, date, text, uuid) from public, anon, authenticated;
grant execute on function public.abonar_meta(uuid, uuid, numeric, date, text, uuid) to service_role;
revoke all on function public.confirmar_recurrente(uuid, uuid, date, date, numeric, date, uuid, boolean) from public, anon, authenticated;
grant execute on function public.confirmar_recurrente(uuid, uuid, date, date, numeric, date, uuid, boolean) to service_role;

-- Comprobación: existe = true, backend = true, navegador = false; la firma anterior de abonar_meta ya no existe
select to_regprocedure('public.abonar_meta(uuid, uuid, numeric, date, text, uuid)') is not null as abonar_existe,
       to_regprocedure('public.abonar_meta(uuid, uuid, numeric, date, text)') is null as firma_anterior_eliminada,
       to_regprocedure('public.confirmar_recurrente(uuid, uuid, date, date, numeric, date, uuid, boolean)') is not null as confirmar_existe,
       has_function_privilege('service_role', 'public.confirmar_recurrente(uuid, uuid, date, date, numeric, date, uuid, boolean)', 'execute') as backend,
       has_function_privilege('anon', 'public.confirmar_recurrente(uuid, uuid, date, date, numeric, date, uuid, boolean)', 'execute')
         or has_function_privilege('authenticated', 'public.confirmar_recurrente(uuid, uuid, date, date, numeric, date, uuid, boolean)', 'execute') as navegador;
