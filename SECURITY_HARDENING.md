# Finanzy — endurecimiento de seguridad (fase 2)

Esta rama parte de la versión más reciente de main y conserva las mejoras recientes de rate limiting, PyJWT/bcrypt y dependencias.

## Incluido
- SECRET_KEY sin default y mínimo de 32 caracteres.
- CORS con orígenes HTTP(S) exactos; sin comodines ni regex globales de Vercel/Codespaces.
- Producción requiere Supabase y DEBUG deshabilitado; no inicializa usuarios demo.
- Apagado controlado de la tarea de limpieza.
- Conserva la implementación PyJWT/bcrypt más reciente de main.
- Alta y recuperación: nueva contraseña de al menos 8 caracteres y máximo 72 bytes.
- Endpoints financieros validan que el usuario exista y esté activo.
- SELECT/UPDATE/DELETE por ID filtran también por usuario_id.
- Se bloquea temporalmente DELETE de cuenta para evitar registros huérfanos hasta definir retención.

## Variables necesarias en Railway antes de desplegar
- ENVIRONMENT=production
- DEBUG=false
- SECRET_KEY: secreto aleatorio nuevo de 32+ caracteres. Rotarlo invalida los JWT actuales.
- CORS_ORIGINS=["https://DOMINIO-REAL-DE-VERCEL"]
- SUPABASE_URL y SUPABASE_KEY (clave secreta solo del backend)
- BREVO_API_KEY y FROM_EMAIL

No publicar SUPABASE_KEY en Vercel ni en variables NEXT_PUBLIC_.

## Pendiente antes de producción
1. Persistir códigos OTP/reset, rate limits y bloqueos de login en almacenamiento compartido/atómico; actualmente permanecen en memoria.
2. Migrar localStorage a cookies HttpOnly con proxy Next.js y protección CSRF.
3. Corregir update_currency que hoy puede simular éxito si falla la escritura.
4. Hacer transaccional el abono a metas.
5. Añadir pruebas automatizadas de aislamiento multiusuario, JWT, OTP, CORS y configuración de producción.
6. Revisar historial Git por secretos históricos y rotar credenciales comprometidas.

No se ha hecho merge ni despliegue. No se han borrado ni reasignado registros existentes.