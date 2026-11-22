# Finanzy — endurecimiento de seguridad (fase 1)

## Variables para Railway (producción)
- ENVIRONMENT=production
- DEBUG=false
- SECRET_KEY: secreto aleatorio propio de al menos 32 caracteres. Rotarlo invalida los JWT actuales.
- ACCESS_TOKEN_EXPIRE_MINUTES=30 (máximo permitido: 1440).
- CORS_ORIGINS=["https://DOMINIO-REAL-DE-VERCEL"] con el host exacto.
- SUPABASE_URL y SUPABASE_KEY. Esta última debe ser la clave secreta de servidor y no debe publicarse.
- BREVO_API_KEY/FROM_EMAIL si el flujo usa Brevo; SENDGRID_API_KEY si el despliegue aún usa SendGrid.

Nunca colocar una clave Supabase secreta/service_role en variables NEXT_PUBLIC_ de Vercel.

## Cambios incluidos
- Se elimina el valor predeterminado inseguro de SECRET_KEY.
- JWT queda fijado en HS256 y exige exp y sub; se usan timestamps UTC.
- Se rechazan contraseñas superiores a 72 bytes UTF-8 para evitar truncamiento bcrypt.
- CORS solo acepta orígenes exactos HTTP(S), sin comodines ni regex de subdominios.
- Producción requiere SUPABASE_URL/SUPABASE_KEY y no inicializa usuarios demo.
- DEBUG queda desactivado por defecto y no se permite activarlo en producción.
- La tarea periódica de limpieza se cancela al apagar FastAPI.

## Pendiente antes de producción (fase 2)
1. Sustituir códigos OTP/verificación/reset en memoria por almacenamiento persistente con intentos atómicos y caducidad.
2. Migrar localStorage a cookies HttpOnly con endpoints de sesión y protección CSRF.
3. Validar existencia/estado activo del usuario en cada solicitud protegida.
4. Añadir filtros usuario_id en cada UPDATE/DELETE del modelo, además de la validación de rutas.
5. Definir borrado de cuenta con política de retención y conciliación; no borrar datos relacionados automáticamente.
6. Añadir pruebas de integración multiusuario, sesión, OTP, recuperación, CORS y producción.
7. Auditar historial Git por secretos antiguos y rotarlos si fueron comprometidos.

No aplicar operaciones destructivas sobre la base de datos de producción.
