# CHG-022 — Limpieza de código sin uso

- **Estado:** aplicado (rama de trabajo; sin commit ni push) · **Modo:** rápido · **Riesgo:** bajo (solo se elimina código muerto, sin cambio de comportamiento)

## Eliminado (verificado con vulture/pyflakes/grep)
1. Variable `MONITOR_SUPABASE_TOKEN` (reservada, sin uso): config, prueba del Monitor, `backend/.env.example`, CT-010 y `CONTEXTO_PROYECTO_CLAUDE.md`.
2. Constante `LOTE_PURGA` de `models/auth_estado.py`.
3. `UserDB.get_by_email` (la app usa `get_by_email_estricto`): también su parche en `tests/conftest.py`, la aserción de `test_auth_estado.py` y las menciones en ADR-010 e INV-039.
4. `porcentajeUso` de `frontend/lib/monitor.ts` y su prueba (la reemplazó `resumenPlan`).
5. Imports sin uso: `timezone` (`test_contadores.py`) y `users_routes` (`test_auth_persistente.py`).
6. `.env.example` de la raíz (vacío; el real es `backend/.env.example`).

## Notas
- Sin cambio de contratos, reglas ni seguridad. Los métodos `limpiar`/`reset`/`limpiar_cache` son ayudas de pruebas y se conservan.
