-- CHG-014 · INV-029 / INV-030 — Registrar ingresos y gastos por WhatsApp con IA
-- Ejecutar en Supabase → SQL Editor ANTES de desplegar el backend que lo usa. No toca datos existentes.
-- Es seguro repetirlo. Cada sentencia funciona sola (el SQL Editor las ejecuta por separado).

-- Número de WhatsApp enlazado a cada cuenta (uno por cuenta, y un número no puede estar en dos cuentas)
create table if not exists public.whatsapp_enlaces (
  usuario_id uuid primary key references public.users(id) on delete cascade,
  telefono varchar(20) not null unique,
  creado_en timestamptz not null default now()
);

-- Mensajes ya procesados: Meta puede reenviar el mismo mensaje, así no se registra dos veces
create table if not exists public.whatsapp_mensajes (
  id varchar(200) primary key,          -- id del mensaje de WhatsApp (wamid)
  usuario_id uuid references public.users(id) on delete cascade,
  recibido_en timestamptz not null default now()
);
create index if not exists idx_whatsapp_mensajes_recibido on public.whatsapp_mensajes(recibido_en);

-- Transacciones creadas por WhatsApp: permiten «deshacer» y «corregir» solo lo que creó el WhatsApp
create table if not exists public.whatsapp_registros (
  transaccion_id uuid primary key references public.transacciones(id) on delete cascade,
  usuario_id uuid not null references public.users(id) on delete cascade,
  lote varchar(200) not null,           -- id del mensaje que lo creó (varios movimientos = un lote)
  creado_en timestamptz not null default now()
);
create index if not exists idx_whatsapp_registros_usuario on public.whatsapp_registros(usuario_id, creado_en desc);

-- Solo el backend (service_role) usa estas tablas
alter table public.whatsapp_enlaces enable row level security;
alter table public.whatsapp_mensajes enable row level security;
alter table public.whatsapp_registros enable row level security;
revoke all on public.whatsapp_enlaces from anon, authenticated;
revoke all on public.whatsapp_mensajes from anon, authenticated;
revoke all on public.whatsapp_registros from anon, authenticated;

-- Comprobación: 3 filas con rowsecurity = true
select tablename, rowsecurity from pg_tables
 where schemaname = 'public' and tablename in ('whatsapp_enlaces', 'whatsapp_mensajes', 'whatsapp_registros');
