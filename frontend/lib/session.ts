/**
 * Constantes de la sesión compartidas por el navegador y el proxy de Next.js (ADR-005).
 *
 * El token (JWT) vive solo en una cookie HttpOnly que el JavaScript del navegador no
 * puede leer. El proxy `app/api/v1/[...path]/route.ts` la convierte en el encabezado
 * `Authorization` al llamar al backend.
 */

/** Encabezado que el navegador debe enviar en toda petición que cambia datos (CSRF). */
export const CSRF_HEADER = 'x-finanzy-csrf'
export const CSRF_VALUE = '1'

/** Datos no sensibles del usuario que el navegador recuerda para pintar la interfaz. */
export const STORED_USER_KEY = 'user'

/** Clave antigua: el token se guardaba en localStorage antes de ADR-005. */
export const LEGACY_TOKEN_KEY = 'token'
