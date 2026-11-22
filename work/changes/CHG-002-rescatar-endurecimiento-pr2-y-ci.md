# CHG-002 — Rescatar el endurecimiento útil del PR #2 y activar CI

- **Estado:** aprobado y fusionado (PR #5, 2026-11-22)
- **Fecha:** 2026-11-22 · **Solicitante:** dueño del proyecto
- **Riesgo:** alto (seguridad, configuración, contrato de usuario) · modo `completo`

## 1. Pedido original (literal)
> si implementa lo que consideres correcto implementar para mi app sin dañar nada pero agregando seguridad a mi app.

(Tras la revisión del PR #2, que se recomendó no fusionar por conflictos y regresiones.)

## 2. Clasificación
Seguridad + deuda técnica · backend (config, sesión, modelos, usuarios), frontend (registro, perfil), CI ·
REQ-N-001, REQ-N-003, REQ-N-004, REQ-N-009, REQ-F-001, REQ-F-011 · BL-004, BL-006, BL-011.

## 3. Análisis
**Qué se toma del PR #2 (adaptado a main):**
- Configuración sin valores inseguros (`SECRET_KEY`, `DEBUG`, CORS, algoritmo). **Diferencia clave con el PR #2:**
  nunca impide arrancar. Lo inseguro se corrige y se avisa con `[CONFIG]` en los logs (INV-019).
  - `SECRET_KEY` vacía o de ejemplo → clave aleatoria temporal (las sesiones se cierran en cada reinicio hasta
    configurar una real). Clave corta propia → se conserva con aviso (cambiarla cerraría las sesiones).
  - `ACCESS_TOKEN_EXPIRE_MINUTES`: se aceptan 5 min a 30 días; 10080 (7 días, REQ-F-002) sigue valiendo.
    El PR #2 limitaba a 1440 y habría tumbado el backend con la configuración actual.
- CORS sin `allow_origin_regex` (`*.vercel.app` dejaba entrar a cualquier proyecto de Vercel) y sin los dominios
  viejos `plataapp*` (BL-011). El frontend usa el proxy de Next.js, así que el navegador no depende de CORS.
- Filtro `usuario_id` en toda consulta por ID de `models/plataapp.py` (defensa en profundidad de INV-001).
- Cuenta activa en cada petición (INV-017), dentro de la consulta que ya hace `get_session_version` (sin consultas extra).
- `PUT /users/me/currency` ya no finge éxito: 503 si la BD no guardó (CT-002). El perfil avisa el error.
- Contraseña de registro 8-128 (INV-018, pregunta abierta 1). Las contraseñas existentes siguen sirviendo para entrar.

**Qué NO se toma del PR #2 y por qué:**
- Bloqueo 409 de `DELETE /users/me`: contradice UC-010/CT-002. El problema real son llaves foráneas que
  probablemente faltan en Supabase → BL-015.
- Volver a crear usuarios demo con `password123`: main los había quitado.
- Workflow que solo compilaba: reemplazado por CI real (BL-004).
- Límite de 72 bytes en contraseñas: `security.py` ya maneja el límite de bcrypt (INV-015).

## 4. Preguntas abiertas
| # | Pregunta | Respuesta | Quién |
|---|---|---|---|
| 1 | ¿Unificar la contraseña mínima en 8? | Sí (decisión delegada: «lo que consideres correcto») | Dueño, 2026-11-22 |
| 2 | ¿Cerrar el PR #2? | Pendiente | Dueño |

## 5. Spec afectada
INV-001 (ampliado), INV-017/018/019 (nuevos) · CT-001 `register` · CT-002 `me/currency` · VALUE-OBJECTS (contraseña) ·
REQUIREMENTS pregunta 1 · TRACEABILITY · BACKLOG (BL-012…016 nuevos).

## 6. Evidencia
- `python -m pytest` (backend): 93 pruebas pasan (64 anteriores + 29 nuevas en `tests/test_endurecimiento.py`).
- `python -m pip_audit -r requirements.txt`: sin vulnerabilidades conocidas.
- `npx eslint .`: 0 problemas · `npx next build`: correcto.

## 7. Despliegue
- No requiere SQL ni variables nuevas. Antes de fusionar, revisar en Railway que `SECRET_KEY` exista (si no, las
  sesiones se cerrarán en cada reinicio) y, tras desplegar, buscar `[CONFIG]` en los logs de Railway.
- Actualizar `CONTEXTO_PROYECTO_CLAUDE.md` §8 (seguridad) y §9 (convenciones de configuración).
