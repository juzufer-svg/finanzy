/**
 * Mensaje legible de un error de axios/FastAPI. Puro (sin React) para poder probarlo con `npm test`; `DialogProvider`
 * lo reexporta como `apiErrorMessage`, que es lo que usan las pantallas.
 */
export function apiErrorMessage(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) {
    // Pydantic antepone «Value error, » al texto de nuestros validadores; solo el de la fecha (INV-063) se muestra tal cual.
    const msg = String(detail[0].msg).replace(/^Value error, /, '')
    if (msg.startsWith('La fecha debe estar entre')) return msg
    return 'Revisa los datos ingresados.'
  }
  if (err?.response?.status === 429) return 'Demasiados intentos. Espera unos minutos.'
  if (!err?.response) return 'No hay conexión con el servidor. Revisa tu internet e intenta de nuevo.'
  return fallback
}
