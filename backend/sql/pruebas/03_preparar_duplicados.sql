-- CHG-013: datos con duplicados para probar 2026-11-23_sin_duplicados.sql
insert into public.users(id, email) values ('66666666-6666-6666-6666-666666666666', 'dup@x');
insert into public.categorias(id, usuario_id, nombre, tipo) values
  ('dddddddd-0000-0000-0000-000000000001', '66666666-6666-6666-6666-666666666666', 'Comida', 'gasto'),
  ('dddddddd-0000-0000-0000-000000000002', '66666666-6666-6666-6666-666666666666', 'Comida', 'gasto'),
  ('dddddddd-0000-0000-0000-000000000003', '66666666-6666-6666-6666-666666666666', 'Comida', 'ingreso');
insert into public.transacciones(usuario_id, categoria_id, monto, fecha, tipo) values
  ('66666666-6666-6666-6666-666666666666', 'dddddddd-0000-0000-0000-000000000001', 10, '2026-11-01', 'gasto'),
  ('66666666-6666-6666-6666-666666666666', 'dddddddd-0000-0000-0000-000000000002', 20, '2026-11-02', 'gasto'),
  ('66666666-6666-6666-6666-666666666666', 'dddddddd-0000-0000-0000-000000000002', 30, '2026-11-03', 'gasto');
insert into public.presupuestos(usuario_id, categoria_id, limite_mensual, mes_ano) values
  ('66666666-6666-6666-6666-666666666666', 'dddddddd-0000-0000-0000-000000000001', 100, '2026-11'),
  ('66666666-6666-6666-6666-666666666666', 'dddddddd-0000-0000-0000-000000000002', 300, '2026-11'),
  ('66666666-6666-6666-6666-666666666666', 'dddddddd-0000-0000-0000-000000000002', 50, '2026-12');
insert into public.recurrentes(usuario_id, categoria_id, tipo, monto, frecuencia, dia_ancla, proxima_fecha) values
  ('66666666-6666-6666-6666-666666666666', 'dddddddd-0000-0000-0000-000000000002', 'gasto', 5, 'mensual', 1, '2026-12-01');
