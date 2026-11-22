-- CHG-001 · INV-016 — Versión de sesión por usuario
-- Ejecutar en Supabase → SQL Editor ANTES de desplegar el backend que la usa.
-- Es segura de repetir (IF NOT EXISTS) y no cierra ninguna sesión: todos empiezan en 0.

alter table public.users
  add column if not exists session_version integer not null default 0;

-- Comprobación: debe mostrar una fila con data_type = integer y column_default = 0
select column_name, data_type, column_default, is_nullable
from information_schema.columns
where table_schema = 'public' and table_name = 'users' and column_name = 'session_version';
