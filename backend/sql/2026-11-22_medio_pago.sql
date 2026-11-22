-- CHG-007 · INV-022 — Medio de pago de las transacciones
-- Ejecutar en Supabase → SQL Editor ANTES de desplegar el backend y el frontend que lo usan.
-- No borra ni cambia datos: agrega una columna opcional (NULL = sin especificar), así que las
-- transacciones existentes y los abonos a metas siguen funcionando igual. Es seguro repetirlo.

alter table public.transacciones
  add column if not exists medio_pago varchar(20);

-- Solo se aceptan estos códigos (la app muestra Débito, Crédito, Efectivo, Transferencia, Nequi / Daviplata)
alter table public.transacciones drop constraint if exists transacciones_medio_pago_check;
alter table public.transacciones
  add constraint transacciones_medio_pago_check
  check (medio_pago is null or medio_pago in ('debito', 'credito', 'efectivo', 'transferencia', 'nequi_daviplata'));

-- Comprobación: una fila con data_type = character varying, is_nullable = YES y sin valor por defecto
select column_name, data_type, is_nullable, column_default
  from information_schema.columns
 where table_schema = 'public' and table_name = 'transacciones' and column_name = 'medio_pago';
