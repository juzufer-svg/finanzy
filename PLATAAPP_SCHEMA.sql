-- Finanzy — Esquema de referencia de la base de datos (Supabase / PostgreSQL)
-- Sirve para crear una base nueva desde cero. Los cambios sobre la base existente se
-- aplican con las migraciones de backend/sql/ (en orden de fecha).

-- Crear tabla users (si no existe)
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) UNIQUE NOT NULL,
  hashed_password VARCHAR(255) NOT NULL,
  full_name VARCHAR(255),
  currency VARCHAR(3) DEFAULT 'USD' CHECK (currency IN ('USD', 'EUR', 'MXN', 'ARS', 'COP', 'CLP')),
  is_active BOOLEAN DEFAULT TRUE,
  session_version INTEGER NOT NULL DEFAULT 0,  -- sube al restablecer la contraseña (INV-016)
  suspendida BOOLEAN NOT NULL DEFAULT FALSE,   -- CHG-023: cuenta suspendida por el administrador
  ultimo_acceso TIMESTAMPTZ,                   -- CHG-023: último inicio de sesión (como mucho una escritura por hora)
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Crear tabla categorias
CREATE TABLE IF NOT EXISTS categorias (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  nombre VARCHAR(100) NOT NULL,
  icono VARCHAR(10),
  tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
  created_at TIMESTAMP DEFAULT NOW()
);

-- Crear tabla transacciones
CREATE TABLE IF NOT EXISTS transacciones (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  categoria_id UUID REFERENCES categorias(id) ON DELETE SET NULL,
  monto NUMERIC(12,2) NOT NULL,
  descripcion TEXT,
  fecha DATE NOT NULL,
  tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
  -- Medio de pago opcional (CHG-007, INV-022); NULL = sin especificar
  medio_pago VARCHAR(20) CONSTRAINT transacciones_medio_pago_check
    CHECK (medio_pago IS NULL OR medio_pago IN ('debito', 'credito', 'efectivo', 'transferencia', 'nequi_daviplata')),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Crear tabla presupuestos
CREATE TABLE IF NOT EXISTS presupuestos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  categoria_id UUID REFERENCES categorias(id) ON DELETE CASCADE NOT NULL,
  limite_mensual NUMERIC(12,2) NOT NULL,
  mes_ano VARCHAR(7) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Crear tabla metas
CREATE TABLE IF NOT EXISTS metas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  nombre VARCHAR(255) NOT NULL,
  monto_objetivo NUMERIC(12,2) NOT NULL,
  monto_actual NUMERIC(12,2) DEFAULT 0,
  fecha_objetivo DATE NOT NULL,
  estado VARCHAR(20) DEFAULT 'en_progreso' CHECK (estado IN ('en_progreso', 'completada', 'cancelada')),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Transacciones recurrentes (CHG-012): plantillas que se proponen y la persona confirma (INV-025)
CREATE TABLE IF NOT EXISTS recurrentes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  categoria_id UUID REFERENCES categorias(id) ON DELETE SET NULL,
  tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
  monto NUMERIC(12,2) NOT NULL CHECK (monto > 0),
  descripcion TEXT NOT NULL DEFAULT '',
  medio_pago VARCHAR(20)
    CHECK (medio_pago IS NULL OR medio_pago IN ('debito', 'credito', 'efectivo', 'transferencia', 'nequi_daviplata')),
  frecuencia VARCHAR(20) NOT NULL CHECK (frecuencia IN ('mensual', 'quincenal', 'semanal')),
  dia_ancla SMALLINT NOT NULL CHECK (dia_ancla BETWEEN 1 AND 31),
  proxima_fecha DATE NOT NULL,
  activa BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE recurrentes ENABLE ROW LEVEL SECURITY;  -- solo el backend (service_role) la usa

-- Crear índices para mejor rendimiento
CREATE INDEX idx_transacciones_usuario ON transacciones(usuario_id);
CREATE INDEX idx_transacciones_fecha ON transacciones(fecha);
CREATE INDEX idx_categorias_usuario ON categorias(usuario_id);
CREATE INDEX idx_presupuestos_usuario ON presupuestos(usuario_id);
CREATE INDEX idx_presupuestos_mes ON presupuestos(mes_ano);
CREATE INDEX idx_metas_usuario ON metas(usuario_id);

-- Índices para los borrados en cascada por categoría
CREATE INDEX idx_transacciones_categoria ON transacciones(categoria_id);
CREATE INDEX idx_presupuestos_categoria ON presupuestos(categoria_id);
CREATE INDEX idx_recurrentes_usuario ON recurrentes(usuario_id);
CREATE INDEX idx_recurrentes_categoria ON recurrentes(categoria_id);

-- Sin duplicados (CHG-013, INV-028)
CREATE UNIQUE INDEX categorias_usuario_nombre_tipo_unico ON categorias(usuario_id, nombre, tipo);
CREATE UNIQUE INDEX presupuestos_usuario_categoria_mes_unico ON presupuestos(usuario_id, categoria_id, mes_ano);

-- Las categorías por defecto las crea el backend para cada usuario la primera vez que las pide
-- (no se insertan aquí: una fila con un usuario inexistente sería un registro huérfano).

-- Crear función para actualizar el campo updated_at automáticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ language 'plpgsql';

-- Crear triggers para updated_at
CREATE TRIGGER update_transacciones_updated_at BEFORE UPDATE ON transacciones
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_presupuestos_updated_at BEFORE UPDATE ON presupuestos
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_metas_updated_at BEFORE UPDATE ON metas
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Habilitar RLS (Row Level Security) si es necesario
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE transacciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE categorias ENABLE ROW LEVEL SECURITY;
ALTER TABLE presupuestos ENABLE ROW LEVEL SECURITY;
ALTER TABLE metas ENABLE ROW LEVEL SECURITY;

-- Sin políticas: el frontend nunca habla con Supabase. Solo el backend accede, con la clave
-- service_role (que no está sujeta a RLS) y verificando el dueño de cada registro (INV-001).
-- Con RLS activo y sin políticas, las claves públicas (anon) no pueden leer ni escribir nada.

-- ── Panel de administración de usuarios (CHG-023, backend/sql/2026-11-25_admin_usuarios.sql) ──
-- Registro de acciones del administrador: SIN llave foránea (sobrevive a la baja) y sin datos personales.
-- Las funciones del panel (admin_*, registrar_acceso) y sus permisos están solo en la migración.
CREATE TABLE IF NOT EXISTS auditoria_admin (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  accion TEXT NOT NULL,
  usuario_id UUID NOT NULL,
  CONSTRAINT auditoria_admin_accion_ck CHECK (accion IN ('suspender', 'reactivar', 'cerrar_sesiones', 'eliminar'))
);
CREATE INDEX IF NOT EXISTS idx_auditoria_admin_creado ON auditoria_admin (creado_en DESC, id DESC);
ALTER TABLE auditoria_admin ENABLE ROW LEVEL SECURITY;

-- ── Cuentas de dinero con saldo derivado (CHG-019 fase a, ADR-009, INV-046 a INV-051) ──
-- Copia de backend/sql/2026-11-25_cuentas.sql (la migración es la fuente al cambiar la base existente):
-- tabla `cuentas`, `transacciones.cuenta_id`, funciones de saldo y disparadores FZ001 a FZ004.
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

-- ── Transferencias entre cuentas de dinero (CHG-024 fase b, ADR-009 puntos 3-5, INV-046 a INV-051) ──
-- Copia de backend/sql/2026-11-25_transferencias.sql (la migración es la fuente al cambiar la base existente):
-- tabla `transferencias`, funciones de saldo con transferencias y disparador FZ001/FZ002.
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
