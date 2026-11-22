# CHG-004 — Abono a metas atómico

- **Estado:** listo-para-aprobar
- **Fecha:** 2026-11-22 · **Solicitante:** dueño del proyecto · **Riesgo:** alto (dinero, base de datos) · modo `completo`

## 1. Pedido original
> si implementa lo que consideres correcto implementar para mi app sin dañar nada pero agregando seguridad a mi app.
(Prioridad 3 del brief de seguridad, BL-013.)

## 2. Problema
`POST /metas/{id}/abonar` leía `monto_actual`, sumaba en Python y escribía; el gasto se creaba aparte. Dos abonos
simultáneos podían perder uno, y una caída entre los pasos podía dejar el gasto sin la suma (se intentaba revertir).

## 3. Diseño
- Función SQL `public.abonar_meta(meta, usuario, monto, fecha, descripcion)` en
  `backend/sql/2026-11-22_abonar_meta_atomico.sql`: valida monto, bloquea la meta del usuario (`FOR UPDATE`),
  busca o crea la categoría «Ahorro», inserta el gasto y suma con `monto_actual + p_monto`, todo en una transacción.
  `SECURITY INVOKER`, `search_path` fijo, `EXECUTE` revocado a `public/anon/authenticated` y dado solo a `service_role`.
- Backend: `MetaDB.abonar` llama la función por RPC. Si no está instalada (PGRST202/42883/42703/42P01) o en modo
  demo, la ruta usa el método anterior: **desplegar en cualquier orden no rompe nada**. Meta ajena → 404 (INV-001).
  Otro error de la BD → 500 (la función ya revirtió todo).
- Duplicados por doble clic: el botón «Abonar» ya se desactiva mientras se guarda.

## 4. Evidencia
- `python -m pytest`: 103 pasan (9 nuevas en `tests/test_metas_atomico.py`).
- PostgreSQL 16 local con el esquema de `PLATAAPP_SCHEMA.sql` y roles como en Supabase:
  - 30 abonos simultáneos de 1 → `monto_actual = 30.00`, 30 transacciones (suma 30.00), una sola categoría «Ahorro», 0 errores.
  - Usuario ajeno → `meta_no_encontrada`, sin cambios. Monto 0 → error, sin cambios. Rol `anon` → `permission denied`.
  - El script se ejecutó dos veces seguidas sin error (se puede repetir).
- No probado contra el Supabase real (requiere ejecutar el SQL; ver §5).

## 4b. Revisión independiente (aprobado, ciclo 1)
Aplicado: bloqueo por usuario (`pg_advisory_xact_lock`) para no crear dos «Ahorro» con abonos simultáneos a metas
distintas (probado: 20 abonos en 2 metas → 10,00 y 10,00, una sola «Ahorro»); id no UUID (22P02) → 404; aviso de no
dar EXECUTE a anon/authenticated; `CONTEXTO_PROYECTO_CLAUDE.md` §4–§8, §10 y §11 actualizados (también por CHG-002/003).
Deuda aceptada (ya existía): tope de monto 1e12 mayor que `NUMERIC(12,2)` y montos con más de 2 decimales → cambio aparte (CT-006).

## 5. Despliegue (en este orden, aunque cualquier orden es seguro)
1. Supabase → SQL Editor → pegar `backend/sql/2026-11-22_abonar_meta_atomico.sql` → Run. La última consulta debe
   mostrar `existe = true, backend = true, navegador_anon = false, navegador_auth = false`.
2. Fusionar el PR (Railway se despliega solo).
3. Abonar a una meta de prueba y revisar que suba el monto y aparezca el gasto en «Ahorro». En los logs de Railway
   **no** debe aparecer `abonar_meta no disponible`.
