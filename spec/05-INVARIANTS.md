# Invariantes

Condiciones que **siempre** deben cumplirse. Se protegen en el backend y se prueban con código
(`backend/tests/`), no dependen de que un agente las recuerde. **Ningún cambio puede debilitarlas** sin un ADR
aprobado por la persona.

| ID | Invariante | Entidad | Dónde se protege | Prueba | Severidad |
|---|---|---|---|---|---|
| INV-001 | Un usuario solo puede ver, editar o eliminar **sus propios** registros; si el registro no existe o es de otro usuario se responde 404 (sin revelar que existe) | Todas | `api/routes/plataapp.py` → `_ensure_owner` | `tests/test_propiedad.py` | Crítica |
| INV-002 | Una transacción o un presupuesto solo puede usar una categoría del mismo usuario | Transacción, Presupuesto | `plataapp.py` → `_ensure_categoria_propia` | `tests/test_propiedad.py` | Crítica |
| INV-003 | Montos > 0 y ≤ 1e12 (transacción, límite, objetivo, abono); monto ahorrado ≥ 0 | Transacción, Presupuesto, Meta | `schemas/plataapp.py` | `tests/test_validaciones.py` | Crítica |
| INV-004 | El tipo de transacción y de categoría es `ingreso` o `gasto` | Transacción, Categoría | `schemas/plataapp.py` (`Literal`) + CHECK en BD | `tests/test_validaciones.py` | Alta |
| INV-005 | Las fechas siguen `YYYY-MM-DD` y los meses `YYYY-MM` | Transacción, Presupuesto, Meta | `schemas/plataapp.py`, `plataapp.py` | `tests/test_validaciones.py` | Alta |
| INV-006 | Una cuenta pendiente nunca obtiene una sesión con el login | Usuario | `api/routes/auth.py` → `login` | `tests/test_auth.py` | Crítica |
| INV-007 | Un código es de un solo uso, vence a los 10 min, se invalida tras 5 intentos fallidos, se genera con `secrets` y los de verificación y de restablecimiento no son intercambiables | Código | `utils/email.py`, `auth.py` | `tests/test_codigos.py` | Crítica |
| INV-008 | Un abono solo se registra si la meta existe y es del usuario; si falla la actualización de la meta, se revierte el gasto creado | Meta, Transacción | `plataapp.py` → `abonar_meta` | `tests/test_metas.py` | Crítica |
| INV-009 | `forgot-password` y `resend-code` responden igual exista o no la cuenta (no revelan correos registrados) | Usuario | `auth.py` | `tests/test_codigos.py` | Alta |
| INV-010 | Límites: 60 s entre códigos al mismo correo; 10 correos/día por destinatario; 10 pedidos de código por IP/hora; 250 correos/día en total; 5 fallos de login por correo → bloqueo 15 min; 30 intentos de credenciales/códigos por IP cada 10 min | Código, Usuario | `core/rate_limit.py`, `auth.py` | `tests/test_limites.py`, `tests/test_auth.py` | Crítica |
| INV-011 | Las sesiones son JWT firmados con HMAC (HS256/384/512) que exigen `exp` y `sub`; se rechazan los vencidos, los sin firma (`alg=none`) y los firmados con otra clave | Sesión | `core/security.py` | `tests/test_auth.py` | Crítica |
| INV-012 | En producción: no hay endpoints de diagnóstico, `/docs` y `/openapi.json` están ocultos, y los códigos nunca se escriben en los logs | Sistema | `main.py`, `utils/email.py` | `tests/test_app_seguridad.py`, `tests/test_correo.py` | Crítica |
| INV-013 | Si la base de datos falla, se responde con error; nunca se guardan datos en memoria cuando Supabase está configurado | Todas | `models/plataapp.py` | `tests/test_app_seguridad.py` | Alta |
| INV-014 | El correo de un usuario es único y se compara y guarda en minúsculas | Usuario | `auth.py`, `models/user.py` + UNIQUE en BD | `tests/test_auth.py` | Alta |
| INV-015 | Las contraseñas solo se guardan como hash bcrypt; los hashes existentes (`$2a$`, `$2b$`, contraseñas > 72 bytes de passlib) siguen validando | Usuario | `core/security.py` | `tests/test_auth.py` | Crítica |
| INV-016 | Al restablecer la contraseña se cierran todas las sesiones abiertas: cada usuario tiene una versión de sesión (`users.session_version`) que sube con el cambio, y un token solo vale si su `sv` coincide con ella (los tokens sin `sv` cuentan como 0). Un token de un usuario que ya no existe se rechaza. Si la BD falla al verificarlo se responde 503, nunca 401 | Usuario, Sesión | `api/sesion.py` → `usuario_de_sesion`, `models/user.py` → `update_password` | `tests/test_sesiones.py` | Crítica |
