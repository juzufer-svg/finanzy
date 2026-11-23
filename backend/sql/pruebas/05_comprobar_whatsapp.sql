-- CHG-014 · INV-029: tablas de WhatsApp (después de 2026-11-23_whatsapp.sql, ejecutado dos veces)
do $$
declare n bigint; u uuid := '77777777-7777-7777-7777-777777777777'; t uuid;
begin
  select count(*) into n from pg_tables where schemaname = 'public'
     and tablename in ('whatsapp_enlaces', 'whatsapp_mensajes', 'whatsapp_registros') and rowsecurity;
  if n <> 3 then raise exception 'tablas de WhatsApp con RLS: % (esperado 3)', n; end if;
  insert into public.users(id, email) values (u, 'wa@x');
  insert into public.whatsapp_enlaces(usuario_id, telefono) values (u, '573001112233');
  begin
    insert into public.whatsapp_enlaces(usuario_id, telefono) values ('88888888-8888-8888-8888-888888888888', '573001112233');
    raise exception 'un número quedó en dos cuentas';
  exception when unique_violation or foreign_key_violation then null;
  end;
  insert into public.whatsapp_mensajes(id, usuario_id) values ('wamid.1', u);
  begin
    insert into public.whatsapp_mensajes(id, usuario_id) values ('wamid.1', u);
    raise exception 'mensaje duplicado aceptado';
  exception when unique_violation then null;
  end;
  insert into public.transacciones(usuario_id, monto, fecha, tipo) values (u, 1, '2026-11-23', 'gasto') returning id into t;
  insert into public.whatsapp_registros(transaccion_id, usuario_id, lote) values (t, u, 'wamid.1');
  delete from public.transacciones where id = t;
  select count(*) into n from public.whatsapp_registros; if n <> 0 then raise exception 'registro no se borró con la transacción'; end if;
  delete from public.users where id = u;
  select (select count(*) from public.whatsapp_enlaces) + (select count(*) from public.whatsapp_mensajes) into n;
  if n <> 0 then raise exception 'CASCADE de usuario no aplicado'; end if;
  raise notice 'OK: tablas de WhatsApp con RLS, sin duplicados y con borrado en cascada';
end $$;
