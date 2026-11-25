-- CHG-029 (BL-017) · INV-003 — Montos como NUMERIC(12,2) (máximo 9 999 999 999,99 y 2 decimales)
-- Ejecutar en Supabase → SQL Editor ANTES de desplegar el backend de CHG-029 (antes del push a main). Pegar COMPLETO.
-- Antes, revisar con 2026-11-25_montos_numeric_12_2_diagnostico.sql (solo lectura).
--
-- Qué hace: convierte transacciones.monto, presupuestos.limite_mensual, metas.monto_objetivo y metas.monto_actual
-- de «numeric» sin precisión a NUMERIC(12,2). No borra ni modifica valores.
--  * Atómica: es un solo bloque; si algo falla no cambia nada.
--  * Segura de repetir: si las 4 columnas ya son NUMERIC(12,2) no toca nada (ni bloquea las tablas).
--  * Bajo bloqueo exclusivo comprueba que no haya valores sobre el tope ni con más de 2 decimales (el ALTER los
--    redondearía en silencio); si los hay, aborta con «montos_invalidos».
--  * Si no consigue el bloqueo en 5 s aborta (55P03): volver a ejecutar en un momento de poco uso.
--  * El disparador fz001_saldo_transacciones depende de «monto» (UPDATE OF): se quita y se vuelve a crear con su
--    misma definición dentro de la misma transacción, con la tabla bloqueada (no hay ventana sin la regla de saldo).
--  * Cualquier otra dependencia no prevista (vista, política, columna generada…) hace fallar el ALTER y nada cambia.
--
-- CÓMO REVERTIR (no pierde datos; no hace falta para volver a la versión anterior del backend, que funciona igual):
-- repetir este bloque cambiando en los ALTER «numeric(12,2)» por «numeric», y la condición de columnas pendientes
-- «(a.atttypid <> 'numeric'::regtype or a.atttypmod <> v_typmod)» por «a.atttypmod = v_typmod» (también quita y recrea el disparador).

do $$
declare
  -- atttypmod de numeric(12,2)
  v_typmod constant integer := ((12 << 16) | 2) + 4;
  v_pendientes integer;
  v_malos text;
  v_trigger text;
  v_estado "char";
begin
  select count(*) into v_pendientes
    from pg_attribute a
   where (a.attrelid, a.attname) in (('public.transacciones'::regclass, 'monto'),
                                     ('public.presupuestos'::regclass, 'limite_mensual'),
                                     ('public.metas'::regclass, 'monto_objetivo'),
                                     ('public.metas'::regclass, 'monto_actual'))
     and (a.atttypid <> 'numeric'::regtype or a.atttypmod <> v_typmod);
  if v_pendientes = 0 then
    return;
  end if;

  perform set_config('lock_timeout', '5s', true);
  -- Mismo orden que abonar_meta (meta y después transacción) para no provocar interbloqueos
  lock table public.metas, public.presupuestos, public.transacciones in access exclusive mode;

  -- «NaN» e infinitos también cuentan como sobre el tope
  select string_agg(columna || ': ' || n, ', ') into v_malos
    from (
      select 'transacciones.monto' as columna, count(*) as n from public.transacciones
       where abs(monto) > 9999999999.99 or monto <> round(monto, 2)
      union all
      select 'presupuestos.limite_mensual', count(*) from public.presupuestos
       where abs(limite_mensual) > 9999999999.99 or limite_mensual <> round(limite_mensual, 2)
      union all
      select 'metas.monto_objetivo', count(*) from public.metas
       where abs(monto_objetivo) > 9999999999.99 or monto_objetivo <> round(monto_objetivo, 2)
      union all
      select 'metas.monto_actual', count(*) from public.metas
       where abs(monto_actual) > 9999999999.99 or monto_actual <> round(monto_actual, 2)
    ) q
   where n > 0;
  if v_malos is not null then
    -- solo cantidades por columna, sin datos de usuarios
    raise exception 'montos_invalidos (filas sobre el tope o con más de 2 decimales): %', v_malos using errcode = '22003';
  end if;

  select pg_get_triggerdef(t.oid), t.tgenabled into v_trigger, v_estado
    from pg_trigger t
   where t.tgrelid = 'public.transacciones'::regclass and t.tgname = 'fz001_saldo_transacciones' and not t.tgisinternal;
  if v_trigger is not null then
    if v_estado <> 'O' then
      raise exception 'fz001_saldo_transacciones no está en su estado normal (%): revisar antes de migrar', v_estado;
    end if;
    drop trigger fz001_saldo_transacciones on public.transacciones;
  end if;

  alter table public.transacciones alter column monto type numeric(12,2);
  alter table public.presupuestos alter column limite_mensual type numeric(12,2);
  alter table public.metas
    alter column monto_objetivo type numeric(12,2),
    alter column monto_actual type numeric(12,2);

  if v_trigger is not null then
    execute v_trigger;
  end if;

  -- La API de Supabase (PostgREST) relee el esquema al confirmar
  notify pgrst, 'reload schema';
end $$;

-- Comprobación: 4 filas con numeric(12,2) y, si las cuentas están instaladas, disparador_saldo = 1
select c.relname as tabla, a.attname as columna, format_type(a.atttypid, a.atttypmod) as tipo,
       (select count(*) from pg_trigger t where t.tgrelid = 'public.transacciones'::regclass
         and t.tgname = 'fz001_saldo_transacciones' and t.tgenabled = 'O') as disparador_saldo
  from pg_attribute a join pg_class c on c.oid = a.attrelid
 where (a.attrelid, a.attname) in (('public.transacciones'::regclass, 'monto'),
                                   ('public.presupuestos'::regclass, 'limite_mensual'),
                                   ('public.metas'::regclass, 'monto_objetivo'),
                                   ('public.metas'::regclass, 'monto_actual'))
 order by 1, 2;
