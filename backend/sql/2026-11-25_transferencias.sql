-- CHG-024 (fase b de CHG-019) · INV-046 a INV-051 · ADR-009 puntos 3-5 — Transferencias entre cuentas de dinero
-- Ejecutar en Supabase → SQL Editor DESPUÉS de 2026-11-25_cuentas.sql y ANTES de desplegar el backend de transferencias.
-- Puede pegarse COMPLETO. Es seguro repetirlo (idempotente) y no toca ninguna fila existente.
--
-- Diseño (ADR-009):
--  * Una transferencia es UNA fila en `transferencias` (no está en `transacciones`: no es ingreso ni gasto, INV-049).
--  * El saldo sigue derivándose (INV-047): se reemplazan `cuenta_saldo_actual` y `cuentas_con_saldo` para sumar las
--    transferencias recibidas y restar las enviadas, sin mirar la fecha. Misma firma y mismos tipos que en la fase (a).
--  * `fz001_saldo_transferencias` (BEFORE INSERT OR DELETE) bloquea origen y destino ORDENADOS por id (así A→B y B→A
--    simultáneas no se interbloquean), evalúa FZ002 bajo el bloqueo y FZ001 solo en la cuenta cuyo saldo baja.
--  * Las llaves compuestas (cuenta_id, usuario_id) son NO ACTION: borrar un usuario (cascada) no choca con ellas y una
--    cuenta con transferencias no se puede eliminar (23503 → «archívala», INV-050).

-- 1. Tabla de transferencias
create table if not exists public.transferencias (
  id uuid primary key default gen_random_uuid(),
  usuario_id uuid not null references public.users(id) on delete cascade,
  cuenta_origen_id uuid not null,
  cuenta_destino_id uuid not null,
  monto numeric(12,2) not null,
  fecha date not null,
  descripcion varchar(255),
  created_at timestamptz not null default now(),
  constraint transferencias_origen_fk foreign key (cuenta_origen_id, usuario_id)
    references public.cuentas (id, usuario_id) on delete no action,
  constraint transferencias_destino_fk foreign key (cuenta_destino_id, usuario_id)
    references public.cuentas (id, usuario_id) on delete no action,
  constraint transferencias_distintas_ck check (cuenta_origen_id <> cuenta_destino_id),
  constraint transferencias_monto_ck check (monto > 0 and monto <= 9999999999.99)
);
-- Índices del saldo (REQ-N-022): INCLUDE (monto, usuario_id) cubre la suma y el filtro por usuario sin leer la tabla.
-- Se recrean (no «if not exists») para que una definición antigua con el mismo nombre no se quede sin avisar.
drop index if exists public.idx_transferencias_origen;
create index idx_transferencias_origen on public.transferencias (cuenta_origen_id) include (monto, usuario_id);
drop index if exists public.idx_transferencias_destino;
create index idx_transferencias_destino on public.transferencias (cuenta_destino_id) include (monto, usuario_id);
-- Lista «más recientes primero» de GET /transferencias
drop index if exists public.idx_transferencias_usuario_fecha;
create index idx_transferencias_usuario_fecha on public.transferencias (usuario_id, fecha desc, created_at desc);

-- 2. Saldo vigente de UNA cuenta, con transferencias. VOLATILE a propósito (ver 2026-11-25_cuentas.sql §3).
create or replace function public.cuenta_saldo_actual(p_cuenta_id uuid)
returns numeric
language sql
volatile
set search_path = public
as $$
  select c.saldo_inicial
         + coalesce((select sum(case t.tipo when 'ingreso' then t.monto when 'gasto' then -t.monto else 0 end)
                       from public.transacciones t where t.cuenta_id = c.id and t.usuario_id = c.usuario_id), 0)
         + coalesce((select sum(x.monto) from public.transferencias x
                      where x.cuenta_destino_id = c.id and x.usuario_id = c.usuario_id), 0)
         - coalesce((select sum(x.monto) from public.transferencias x
                      where x.cuenta_origen_id = c.id and x.usuario_id = c.usuario_id), 0)
    from public.cuentas c where c.id = p_cuenta_id
$$;

-- 3. Listado con saldo (INV-047): UNA consulta agregada; mismas columnas que en la fase (a).
create or replace function public.cuentas_con_saldo(p_usuario_id uuid)
returns table (id uuid, usuario_id uuid, nombre varchar, tipo varchar, saldo_inicial numeric,
               archivada boolean, created_at timestamptz, saldo numeric)
language sql
stable
set search_path = public
as $$
  select c.id, c.usuario_id, c.nombre, c.tipo, c.saldo_inicial, c.archivada, c.created_at,
         c.saldo_inicial + coalesce(m.neto, 0) + coalesce(r.recibido, 0) - coalesce(e.enviado, 0) as saldo
    from public.cuentas c
    left join lateral (
      select sum(case t.tipo when 'ingreso' then t.monto when 'gasto' then -t.monto else 0 end) as neto
        from public.transacciones t where t.cuenta_id = c.id and t.usuario_id = c.usuario_id) m on true
    left join lateral (
      select sum(x.monto) as recibido
        from public.transferencias x where x.cuenta_destino_id = c.id and x.usuario_id = c.usuario_id) r on true
    left join lateral (
      select sum(x.monto) as enviado
        from public.transferencias x where x.cuenta_origen_id = c.id and x.usuario_id = c.usuario_id) e on true
   where c.usuario_id = p_usuario_id
   order by lower(c.nombre), c.id
$$;

-- 4. Disparador de transferencias (BEFORE): bloqueo ordenado → FZ002 → FZ001
create or replace function public.fz001_saldo_transferencias_fn()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  v_uid uuid;
  v_ori uuid;
  v_des uuid;
  v_monto numeric;
  v_ids uuid[];
  r record;
  v_delta numeric;
begin
  if tg_op = 'DELETE' then
    v_uid := old.usuario_id; v_ori := old.cuenta_origen_id; v_des := old.cuenta_destino_id; v_monto := old.monto;
    -- Cascada de borrar el usuario (REQ-F-013, INV-021): ya no existe, no hay nada que proteger
    if not exists (select 1 from public.users u where u.id = v_uid) then return old; end if;
  else
    v_uid := new.usuario_id; v_ori := new.cuenta_origen_id; v_des := new.cuenta_destino_id; v_monto := new.monto;
  end if;
  select array_agg(x order by x) into v_ids from (select distinct x from unnest(array[v_ori, v_des]) x where x is not null) q;

  -- (i) PRIMER paso: bloquear origen y destino del propio usuario, ordenados por id (A→B y B→A no se interbloquean).
  -- Una cuenta ajena o inexistente no se bloquea: la llave foránea compuesta rechazará la fila.
  perform 1 from public.cuentas c where c.id = any (v_ids) and c.usuario_id = v_uid order by c.id for update;

  -- (ii) con el bloqueo tomado: archivada = congelada (FZ002), también al eliminar
  for r in select c.id, c.archivada from public.cuentas c
            where c.id = any (v_ids) and c.usuario_id = v_uid order by c.id loop
    if r.archivada then
      raise exception 'cuenta_archivada' using errcode = 'FZ002', detail = r.id::text;
    end if;
  end loop;

  -- (iii) FZ001 solo en la cuenta cuyo saldo BAJA (alta: el origen; baja: el destino), salvo tarjeta de crédito
  for r in select c.id, c.tipo from public.cuentas c
            where c.id = any (v_ids) and c.usuario_id = v_uid order by c.id loop
    if r.tipo = 'tarjeta_credito' then continue; end if;
    v_delta := 0;
    if r.id = v_ori then v_delta := v_delta + case tg_op when 'INSERT' then -v_monto else v_monto end; end if;
    if r.id = v_des then v_delta := v_delta + case tg_op when 'INSERT' then v_monto else -v_monto end; end if;
    if v_delta < 0 and public.cuenta_saldo_actual(r.id) + v_delta < 0 then
      raise exception 'saldo_negativo' using errcode = 'FZ001', detail = r.id::text;
    end if;
  end loop;

  if tg_op = 'DELETE' then return old; end if;
  return new;
end $$;

drop trigger if exists fz001_saldo_transferencias on public.transferencias;
create trigger fz001_saldo_transferencias
  before insert or delete on public.transferencias
  for each row execute function public.fz001_saldo_transferencias_fn();

-- 5. Solo el backend (service_role) usa la tabla y las funciones; RLS activado SIN políticas (INV-021)
do $$
declare f text;
  funciones text[] := array[
    'public.cuenta_saldo_actual(uuid)',
    'public.cuentas_con_saldo(uuid)',
    'public.fz001_saldo_transferencias_fn()'];
begin
  alter table public.transferencias enable row level security;
  revoke all on public.transferencias from public;
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on public.transferencias from anon;
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    revoke all on public.transferencias from authenticated;
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant all on public.transferencias to service_role;
  end if;
  foreach f in array funciones loop
    execute format('revoke all on function %s from public', f);
    if exists (select 1 from pg_roles where rolname = 'anon') then
      execute format('revoke all on function %s from anon', f);
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
      execute format('revoke all on function %s from authenticated', f);
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
      execute format('grant execute on function %s to service_role', f);
    end if;
  end loop;
end $$;

-- Comprobación: transferencias con rowsecurity = true; 1 disparador; 0 transferencias al migrar
select tablename, rowsecurity from pg_tables where schemaname = 'public' and tablename = 'transferencias';
select tgname from pg_trigger where tgname = 'fz001_saldo_transferencias' and not tgisinternal;
select count(*) as transferencias from public.transferencias;
