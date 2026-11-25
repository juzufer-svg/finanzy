# Estado actual (traspaso de sesión)

> Se actualiza al cerrar cada cambio. Para retomar: leer este archivo y `docs/MAPA.md`; nada más hasta tener una tarea.

**Fecha:** 2026-11-25 · **`origin/main`:** `22a4bf8` y el commit de estado que lo sigue (CHG-028, ahorro de tokens; el último commit real se ve con `git log -1 origin/main`). Cada push a `main` despliega (Vercel + Railway).
**Rama de trabajo:** `claude/practical-johnson-qeg8wd`, adelantada a `main` con CHG-029. No hacer push a `main` sin aprobación del dueño.

## Desplegado en `main` (verificar en producción tras cada push)
Auth persistente (CHG-020), exportar (CHG-018), cuentas con saldo, transferencias y fase (c) (CHG-019/024/025), panel de usuarios del Dueño (CHG-023), ejecutor propio de transacciones (CHG-026), rango de fechas (CHG-027), Monitor (CHG-017).

## Migraciones SQL (`backend/sql/`)
- Aplicadas en Supabase: todas las anteriores del repo y `2026-11-25_cuentas.sql`, `2026-11-25_transferencias.sql`, `2026-11-25_cuentas_integracion.sql`.
- `2026-11-25_admin_usuarios.sql`: aplicada y verificada en Supabase (8 funciones de admin, columnas `users.suspendida` y `ultimo_acceso`, tabla `auditoria_admin`).
- Regla: el SQL se ejecuta ANTES del push que lo usa.

## Cambio en curso
- CHG-029 (tope de montos, BL-017): verificado en la rama. Falta, con aprobación del dueño: diagnóstico → migración `backend/sql/2026-11-25_montos_numeric_12_2.sql` en Supabase → comprobación → push a `main`.

## Fichas
`work/changes/` tiene CHG-029; las demás están en `work/archivo/`.

## Pendientes abiertos (`work/BACKLOG.md`)
BL-005 (RLS con Security Advisor), BL-008 (columna `metas.estado`), BL-016 (cerrar PR #2), BL-017 (tope de montos 1e12), BL-019 (columna `mes_año`), BL-032 (asistente en la moneda elegida), BL-036, BL-040 (limitadores en memoria), BL-044 (tope por usuario en cuentas), BL-048 (modo demo sin Supabase en producción).

## Riesgos aceptados
BL-044 (4 hilos de cuentas compartidos), BL-040 (limitadores del asistente, WhatsApp y Monitor en memoria), BL-048 (rutas de finanzas caen a modo demo si no hay Supabase).

## Siguiente paso sugerido
1. Cerrar CHG-029 (aprobación, migración y despliegue). 2. Abrir una sesión nueva leyendo solo este archivo y `docs/MAPA.md`.
