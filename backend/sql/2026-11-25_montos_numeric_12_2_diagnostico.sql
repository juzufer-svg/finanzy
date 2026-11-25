-- CHG-029 — Diagnóstico de SOLO LECTURA previo a 2026-11-25_montos_numeric_12_2.sql (no cambia nada).
-- Una sola consulta (el SQL Editor muestra solo el último resultado). Esperado:
--   «tipo»: las 4 columnas con su tipo actual (numeric)
--   «dependencia»: sobre transacciones.monto, el disparador fz001_saldo_transacciones y el índice
--                  idx_transacciones_cuenta (el ALTER lo reconstruye solo); además valores por defecto (metas.monto_actual),
--                  índices y restricciones CHECK, que PostgreSQL revalida solo. Cualquier vista (rule), política, columna generada, función u otro
--                  disparador: DETENERSE y revisar antes de migrar.
--   «invalidos»: 0 en todas
with col(tabla, columna) as (
  values ('public.transacciones'::regclass, 'monto'::name), ('public.presupuestos'::regclass, 'limite_mensual'),
         ('public.metas'::regclass, 'monto_objetivo'), ('public.metas'::regclass, 'monto_actual')
), att as (
  select c.tabla, c.columna, a.attnum, format_type(a.atttypid, a.atttypmod) as tipo
    from col c join pg_attribute a on a.attrelid = c.tabla and a.attname = c.columna
)
select 'tipo' as seccion, tabla::text || '.' || columna as columna, tipo as detalle from att
union all
select 'dependencia', att.tabla::text || '.' || att.columna, pg_describe_object(d.classid, d.objid, d.objsubid)
  from att join pg_depend d on d.refclassid = 'pg_class'::regclass and d.refobjid = att.tabla and d.refobjsubid = att.attnum
union all
select 'invalidos', 'transacciones.monto', count(*)::text from public.transacciones
 where abs(monto) > 9999999999.99 or monto <> round(monto, 2)
union all
select 'invalidos', 'presupuestos.limite_mensual', count(*)::text from public.presupuestos
 where abs(limite_mensual) > 9999999999.99 or limite_mensual <> round(limite_mensual, 2)
union all
select 'invalidos', 'metas.monto_objetivo', count(*)::text from public.metas
 where abs(monto_objetivo) > 9999999999.99 or monto_objetivo <> round(monto_objetivo, 2)
union all
select 'invalidos', 'metas.monto_actual', count(*)::text from public.metas
 where abs(monto_actual) > 9999999999.99 or monto_actual <> round(monto_actual, 2)
order by 1, 2, 3;
