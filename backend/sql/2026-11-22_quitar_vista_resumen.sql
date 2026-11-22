-- CHG-005 — Quitar la vista sin uso public.v_resumen_mensual (si existe)
-- Ejecutar en Supabase → SQL Editor. No borra datos: una vista es solo una consulta guardada.
--
-- Por qué: el esquema antiguo (PLATAAPP_SCHEMA.sql) creaba esta vista con los totales de
-- ingresos y gastos de TODOS los usuarios. Ningún código de Finanzy la usa. En Supabase las
-- vistas del esquema public se publican por la API y, salvo que se creen con
-- security_invoker, ignoran RLS; el "Security Advisor" de Supabase la marca como riesgo.

-- 1) ¿Existe? (si no sale ninguna fila, no hace falta seguir)
select table_schema, table_name from information_schema.views
 where table_schema = 'public' and table_name = 'v_resumen_mensual';

-- 2) Quitarla
drop view if exists public.v_resumen_mensual;
