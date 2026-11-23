-- CHG-012 · INV-025 / INV-026 — Transacciones recurrentes (arriendo, sueldo, suscripciones…)
-- Ejecutar en Supabase → SQL Editor ANTES de desplegar el backend y el frontend que la usan.
-- No toca datos existentes: solo crea la tabla nueva. Es seguro repetirlo.
--
-- Cada fila es una "plantilla": cuando llega su próxima fecha, la app la muestra como
-- pendiente y la persona la confirma (crea la transacción) u omite. Nunca se registra sola.

create table if not exists public.recurrentes (
  id uuid primary key default gen_random_uuid(),
  usuario_id uuid not null references public.users(id) on delete cascade,
  -- Borrar la categoría no borra la recurrente: queda "sin categoría", igual que las transacciones
  categoria_id uuid references public.categorias(id) on delete set null,
  tipo varchar(20) not null check (tipo in ('ingreso', 'gasto')),
  monto numeric(12,2) not null check (monto > 0),
  descripcion text not null default '',
  medio_pago varchar(20)
    check (medio_pago is null or medio_pago in ('debito', 'credito', 'efectivo', 'transferencia', 'nequi_daviplata')),
  frecuencia varchar(20) not null check (frecuencia in ('mensual', 'quincenal', 'semanal')),
  -- Día del mes de referencia (el de la primera fecha): evita que un 31 se vuelva 28 para siempre tras febrero
  dia_ancla smallint not null check (dia_ancla between 1 and 31),
  proxima_fecha date not null,
  activa boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists idx_recurrentes_usuario on public.recurrentes(usuario_id);
create index if not exists idx_recurrentes_categoria on public.recurrentes(categoria_id);

-- Solo el backend (service_role) lee y escribe esta tabla. Con RLS activo y sin políticas,
-- las claves anon/authenticated de Supabase no pueden ver ni cambiar nada (service_role no se ve afectada).
alter table public.recurrentes enable row level security;
revoke all on public.recurrentes from anon, authenticated;

-- Comprobación: debe mostrar la tabla con rowsecurity = true
select tablename, rowsecurity from pg_tables where schemaname = 'public' and tablename = 'recurrentes';
