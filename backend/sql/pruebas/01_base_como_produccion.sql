-- Prueba automática de las migraciones de huérfanos (CHG-005). La corre GitHub Actions (CI) sobre un
-- PostgreSQL vacío y desechable; NUNCA ejecutar en Supabase (borra el esquema public).
-- Imita la base real: sin llaves foráneas de usuario, con la columna "mes_año", una llave NO ACTION previa
-- y los 64 huérfanos (53/9/1/1), más un movimiento real que apunta a una categoría huérfana.
-- Protección: solo corre en la base desechable que crea probar.sh.
do $$ begin
  if current_database() <> 'finanzy_prueba_sql' then
    raise exception 'Este archivo solo se ejecuta en la base de prueba finanzy_prueba_sql (estás en %)', current_database();
  end if;
end $$;
drop schema if exists respaldo cascade;
drop schema public cascade;
create schema public;
create extension if not exists pgcrypto;
do $$ begin if not exists (select 1 from pg_roles where rolname='anon') then create role anon; end if;
if not exists (select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if; end $$;
create table users (id uuid primary key default gen_random_uuid(), email text unique);
create table categorias (id uuid primary key default gen_random_uuid(), usuario_id uuid, nombre varchar(100), icono varchar(10), tipo varchar(20), created_at timestamp default now());
create table transacciones (id uuid primary key default gen_random_uuid(), usuario_id uuid, categoria_id uuid references categorias(id), monto numeric(12,2), descripcion text, fecha date, tipo varchar(20), created_at timestamp default now(), updated_at timestamp default now());
create table presupuestos (id uuid primary key default gen_random_uuid(), usuario_id uuid, categoria_id uuid, limite_mensual numeric(12,2), mes_ano varchar(7), "mes_año" varchar(7));
create table metas (id uuid primary key default gen_random_uuid(), usuario_id uuid, nombre text, monto_objetivo numeric, monto_actual numeric default 0, fecha_objetivo date, estado varchar(20));
insert into users(id,email) values ('11111111-1111-1111-1111-111111111111','a@x');
-- real user data
insert into categorias(id,usuario_id,nombre,tipo) values ('aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111','Comida','gasto');
insert into transacciones(usuario_id,categoria_id,monto,fecha,tipo) values ('11111111-1111-1111-1111-111111111111','aaaaaaaa-0000-0000-0000-000000000001',10,'2026-11-01','gasto');
insert into presupuestos(usuario_id,categoria_id,limite_mensual,mes_ano) values ('11111111-1111-1111-1111-111111111111','aaaaaaaa-0000-0000-0000-000000000001',100,'2026-11');
insert into metas(usuario_id,nombre,monto_objetivo,fecha_objetivo) values ('11111111-1111-1111-1111-111111111111','Viaje',100,'2027-01-01');
-- orphans: 53 categorias, 9 transacciones, 1 presupuesto, 1 meta
insert into categorias(usuario_id,nombre,tipo) select '00000000-0000-0000-0000-000000000000','x'||g,'gasto' from generate_series(1,52) g;
insert into categorias(id,usuario_id,nombre,tipo) values ('bbbbbbbb-0000-0000-0000-000000000001','22222222-2222-2222-2222-222222222222','huerf','gasto');
insert into transacciones(usuario_id,monto,fecha,tipo) select '22222222-2222-2222-2222-222222222222',5,'2026-10-01','gasto' from generate_series(1,8);
insert into transacciones(usuario_id,categoria_id,monto,fecha,tipo) values (null,'bbbbbbbb-0000-0000-0000-000000000001',5,'2026-10-01','gasto');
-- real user's tx pointing to orphan category
insert into transacciones(usuario_id,categoria_id,monto,fecha,tipo) values ('11111111-1111-1111-1111-111111111111','bbbbbbbb-0000-0000-0000-000000000001',7,'2026-11-02','gasto');
insert into presupuestos(usuario_id,categoria_id,limite_mensual,mes_ano) values ('22222222-2222-2222-2222-222222222222','bbbbbbbb-0000-0000-0000-000000000001',1,'2026-10');
insert into metas(usuario_id,nombre,monto_objetivo,fecha_objetivo) values ('22222222-2222-2222-2222-222222222222','x',1,'2027-01-01');
