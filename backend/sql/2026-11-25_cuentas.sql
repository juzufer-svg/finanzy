-- CHG-019 fase (a) · INV-046 a INV-051 · ADR-009 — Cuentas de dinero con saldo derivado
-- Ejecutar en Supabase → SQL Editor ANTES de desplegar el backend de la fase (a). Puede pegarse COMPLETO.
-- Es seguro repetirlo (idempotente). NO toca ninguna fila existente: `transacciones.cuenta_id` empieza en NULL
-- (las transacciones anteriores quedan «sin cuenta» y no mueven ningún saldo).
--
-- Diseño (ADR-009):
--  * El saldo se DERIVA (saldo_inicial + ingresos − gastos), no se guarda (INV-047). Aún no hay transferencias (fase b).
--  * La regla «solo la tarjeta de crédito puede quedar en negativo» y «archivada = congelada» viven en disparadores
--    BEFORE con prefijo fz001_. Su PRIMER paso es bloquear (FOR UPDATE, ordenado por id) las cuentas implicadas, antes de
--    que corra ninguna llave foránea (que son disparadores AFTER internos): así las escrituras simultáneas hacen cola
--    sin subir bloqueos y no se interbloquean (un disparador AFTER dio 27 `deadlock detected` en el prototipo).
--  * Errores propios (SQLSTATE): FZ001 saldo negativo · FZ002 cuenta archivada · FZ003 tope de 20 cuentas por usuario ·
--    FZ004 el tipo y el dueño de una cuenta existente no se pueden cambiar.
--  * La llave foránea de cuenta_id es compuesta (cuenta_id, usuario_id) y ON DELETE NO ACTION (no RESTRICT): así borrar un
--    usuario (REQ-F-013, cascada) no choca con sus cuentas ni con sus transacciones (INV-021).

-- 1. Tabla de cuentas de dinero
create table if not exists public.cuentas (
  id uuid primary key default gen_random_uuid(),
  usuario_id uuid not null references public.users(id) on delete cascade,
  nombre varchar(100) not null,
  tipo varchar(20) not null,
  saldo_inicial numeric(12,2) not null default 0,
  archivada boolean not null default false,
  created_at timestamptz not null default now(),
  constraint cuentas_id_usuario_uk unique (id, usuario_id),
  constraint cuentas_nombre_ck check (char_length(btrim(nombre)) between 1 and 100),
  constraint cuentas_tipo_ck check (tipo in ('efectivo', 'ahorros_corriente', 'billetera_digital', 'tarjeta_credito')),
  -- INV-051: tope real de NUMERIC(12,2); saldo inicial negativo solo en la tarjeta de crédito (deuda inicial)
  constraint cuentas_saldo_inicial_ck check (
    saldo_inicial between -9999999999.99 and 9999999999.99
    and (saldo_inicial >= 0 or tipo = 'tarjeta_credito'))
);
-- Nombre único por usuario sin distinguir mayúsculas ni espacios sobrantes (INV-050)
create unique index if not exists idx_cuentas_usuario_nombre on public.cuentas (usuario_id, lower(btrim(nombre)));

-- 2. cuenta_id en transacciones: opcional, llave compuesta (la BD impide usar la cuenta de otro usuario, INV-046)
alter table public.transacciones add column if not exists cuenta_id uuid;
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'transacciones_cuenta_fk' and conrelid = 'public.transacciones'::regclass) then
    alter table public.transacciones add constraint transacciones_cuenta_fk
      foreign key (cuenta_id, usuario_id) references public.cuentas (id, usuario_id) on delete no action;
  end if;
  -- La llave compuesta es MATCH SIMPLE: con usuario_id nulo no se comprobaría; se cierra ese hueco
  if not exists (select 1 from pg_constraint where conname = 'transacciones_cuenta_usuario_ck' and conrelid = 'public.transacciones'::regclass) then
    alter table public.transacciones add constraint transacciones_cuenta_usuario_ck
      check (cuenta_id is null or usuario_id is not null);
  end if;
end $$;
-- Índice para el saldo (REQ-N-022): solo las transacciones con cuenta; INCLUDE (tipo, monto, usuario_id) cubre también el
-- filtro `t.usuario_id = c.usuario_id` de las consultas de saldo, así que no hace falta leer la tabla
create index if not exists idx_transacciones_cuenta on public.transacciones (cuenta_id) include (tipo, monto, usuario_id) where cuenta_id is not null;

-- 3. Saldo vigente de UNA cuenta. VOLATILE a propósito: debe ver lo confirmado por quien tenía el bloqueo antes
-- (una función STABLE usaría la instantánea de la sentencia que la llama, tomada ANTES de esperar el bloqueo).
create or replace function public.cuenta_saldo_actual(p_cuenta_id uuid)
returns numeric
language sql
volatile
set search_path = public
as $$
  select c.saldo_inicial + coalesce((
           select sum(case t.tipo when 'ingreso' then t.monto when 'gasto' then -t.monto else 0 end)
             from public.transacciones t where t.cuenta_id = c.id and t.usuario_id = c.usuario_id), 0)
    from public.cuentas c where c.id = p_cuenta_id
$$;

-- 4. Listado con saldo (INV-047): UNA consulta agregada; solo las columnas de la lista blanca de CT-012.
-- Cuentan TODAS las transacciones con esa cuenta, aunque su fecha sea futura. (La fase b sumará las transferencias.)
create or replace function public.cuentas_con_saldo(p_usuario_id uuid)
returns table (id uuid, usuario_id uuid, nombre varchar, tipo varchar, saldo_inicial numeric,
               archivada boolean, created_at timestamptz, saldo numeric)
language sql
stable
set search_path = public
as $$
  select c.id, c.usuario_id, c.nombre, c.tipo, c.saldo_inicial, c.archivada, c.created_at,
         c.saldo_inicial + coalesce(m.neto, 0) as saldo
    from public.cuentas c
    left join lateral (
      select sum(case t.tipo when 'ingreso' then t.monto when 'gasto' then -t.monto else 0 end) as neto
        from public.transacciones t where t.cuenta_id = c.id and t.usuario_id = c.usuario_id) m on true
   where c.usuario_id = p_usuario_id
   order by lower(c.nombre), c.id
$$;

-- 5. Disparador de transacciones (BEFORE): bloqueo ordenado → FZ002 → FZ001
create or replace function public.fz001_saldo_transacciones_fn()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  v_uid uuid;
  v_ids uuid[] := '{}';
  r record;
  v_delta numeric;
begin
  if tg_op = 'DELETE' then
    v_uid := old.usuario_id;
    if old.cuenta_id is null then return old; end if;
    -- Cascada de borrar el usuario (REQ-F-013, INV-021): ya no existe, no hay nada que proteger
    if not exists (select 1 from public.users u where u.id = v_uid) then return old; end if;
    v_ids := array[old.cuenta_id];
  elsif tg_op = 'INSERT' then
    v_uid := new.usuario_id;
    if new.cuenta_id is null then return new; end if;
    v_ids := array[new.cuenta_id];
  else
    v_uid := new.usuario_id;
    -- Sin cambio real de monto, tipo ni cuenta (p. ej. un PUT que reenvía los mismos valores) no hay nada que comprobar
    if new.monto is not distinct from old.monto and new.tipo is not distinct from old.tipo
       and new.cuenta_id is not distinct from old.cuenta_id then
      return new;
    end if;
    if old.cuenta_id is null and new.cuenta_id is null then return new; end if;
    select coalesce(array_agg(x order by x), '{}') into v_ids
      from (select distinct x from unnest(array[old.cuenta_id, new.cuenta_id]) x where x is not null) q;
  end if;

  -- (i) PRIMER paso: bloquear las cuentas del propio usuario implicadas, ordenadas por id (sin interbloqueos).
  -- Una cuenta ajena o inexistente no se bloquea: la llave foránea compuesta rechazará la fila.
  perform 1 from public.cuentas c where c.id = any (v_ids) and c.usuario_id = v_uid order by c.id for update;

  -- (ii) con el bloqueo tomado: archivada = congelada (FZ002) y regla de saldo (FZ001)
  for r in select c.id, c.tipo, c.archivada from public.cuentas c
            where c.id = any (v_ids) and c.usuario_id = v_uid order by c.id loop
    if r.archivada then
      raise exception 'cuenta_archivada' using errcode = 'FZ002', detail = r.id::text;
    end if;
  end loop;
  for r in select c.id, c.tipo from public.cuentas c
            where c.id = any (v_ids) and c.usuario_id = v_uid order by c.id loop
    if r.tipo = 'tarjeta_credito' then continue; end if;
    -- efecto de ESTA fila sobre el saldo de la cuenta r.id (el BEFORE aún no la ve): nuevo − viejo
    v_delta := 0;
    if tg_op <> 'DELETE' and new.cuenta_id = r.id then
      v_delta := v_delta + case new.tipo when 'ingreso' then new.monto when 'gasto' then -new.monto else 0 end;
    end if;
    if tg_op <> 'INSERT' and old.cuenta_id = r.id then
      v_delta := v_delta - case old.tipo when 'ingreso' then old.monto when 'gasto' then -old.monto else 0 end;
    end if;
    -- Solo se comprueba la cuenta cuyo saldo BAJA
    if v_delta < 0 and public.cuenta_saldo_actual(r.id) + v_delta < 0 then
      raise exception 'saldo_negativo' using errcode = 'FZ001', detail = r.id::text;
    end if;
  end loop;

  if tg_op = 'DELETE' then return old; end if;
  return new;
end $$;

drop trigger if exists fz001_saldo_transacciones on public.transacciones;
create trigger fz001_saldo_transacciones
  before insert or update of monto, tipo, cuenta_id or delete on public.transacciones
  for each row execute function public.fz001_saldo_transacciones_fn();

-- 6. Disparador de cuentas (BEFORE): bajar el saldo inicial no puede dejar el saldo en negativo (FZ001)
create or replace function public.fz001_saldo_cuentas_fn()
returns trigger
language plpgsql
set search_path = public
as $$
declare v_tipo text;
begin
  if new.saldo_inicial is not distinct from old.saldo_inicial or new.saldo_inicial >= old.saldo_inicial then
    return new;
  end if;
  select c.tipo into v_tipo from public.cuentas c where c.id = old.id for update;
  if v_tipo is null or v_tipo = 'tarjeta_credito' then return new; end if;
  if public.cuenta_saldo_actual(old.id) + (new.saldo_inicial - old.saldo_inicial) < 0 then
    raise exception 'saldo_negativo' using errcode = 'FZ001', detail = old.id::text;
  end if;
  return new;
end $$;

drop trigger if exists fz001_saldo_cuentas on public.cuentas;
create trigger fz001_saldo_cuentas
  before update of saldo_inicial on public.cuentas
  for each row execute function public.fz001_saldo_cuentas_fn();

-- 7. Tope de 20 cuentas por usuario (FZ003), también con altas simultáneas (bloqueo por usuario hasta confirmar)
create or replace function public.fz003_tope_cuentas_fn()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended('fz003_tope_cuentas:' || new.usuario_id::text, 0));
  if (select count(*) from public.cuentas c where c.usuario_id = new.usuario_id) >= 20 then
    raise exception 'tope_cuentas' using errcode = 'FZ003';
  end if;
  return new;
end $$;

drop trigger if exists fz003_tope_cuentas on public.cuentas;
create trigger fz003_tope_cuentas
  before insert on public.cuentas
  for each row execute function public.fz003_tope_cuentas_fn();

-- 7b. El tipo y el dueño de una cuenta existente no cambian nunca (FZ004): cambiar efectivo → tarjeta de crédito, o una
-- tarjeta con saldo negativo → efectivo, burlaría la regla de saldo (INV-048). La API ya nunca los envía; esto cierra el UPDATE directo.
create or replace function public.fz004_cuenta_inmutable_fn()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.tipo is distinct from old.tipo or new.usuario_id is distinct from old.usuario_id then
    raise exception 'cuenta_inmutable' using errcode = 'FZ004', detail = old.id::text;
  end if;
  return new;
end $$;

drop trigger if exists fz004_cuenta_inmutable on public.cuentas;
create trigger fz004_cuenta_inmutable
  before update of tipo, usuario_id on public.cuentas
  for each row execute function public.fz004_cuenta_inmutable_fn();

-- 8. Solo el backend (service_role) usa la tabla y las funciones; RLS activado SIN políticas (INV-021)
do $$
declare f text;
  funciones text[] := array[
    'public.cuenta_saldo_actual(uuid)',
    'public.cuentas_con_saldo(uuid)',
    'public.fz001_saldo_transacciones_fn()',
    'public.fz001_saldo_cuentas_fn()',
    'public.fz003_tope_cuentas_fn()',
    'public.fz004_cuenta_inmutable_fn()'];
begin
  alter table public.cuentas enable row level security;
  revoke all on public.cuentas from public;
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on public.cuentas from anon;
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    revoke all on public.cuentas from authenticated;
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant all on public.cuentas to service_role;
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

-- Comprobación: cuentas con rowsecurity = true; 4 disparadores; 0 transacciones con cuenta_id
select tablename, rowsecurity from pg_tables where schemaname = 'public' and tablename = 'cuentas';
select tgname from pg_trigger where tgname in ('fz001_saldo_transacciones', 'fz001_saldo_cuentas', 'fz003_tope_cuentas', 'fz004_cuenta_inmutable') and not tgisinternal order by 1;
select count(*) as transacciones_con_cuenta from public.transacciones where cuenta_id is not null;
