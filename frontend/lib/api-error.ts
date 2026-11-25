const MSG_MONTO_TOPE = 'El monto debe tener máximo 2 decimales y no superar $9.999.999.999,99 (pesos colombianos)'

/**
 * Mensaje legible de un error de axios/FastAPI. Puro (sin React) para poder probarlo con `npm test`; `DialogProvider`
 * lo reexporta como `apiErrorMessage`, que es lo que usan las pantallas.
 */
export function apiErrorMessage(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) {
    // Pydantic antepone «Value error, » al texto de nuestros validadores; solo el de la fecha (INV-063) y el del tope de montos
    // (INV-003) se muestran tal cual.
    const msg = String(detail[0].msg).replace(/^Value error, /, '')
    if (msg.startsWith('La fecha debe estar entre') || msg === MSG_MONTO_TOPE) return msg
    return 'Revisa los datos ingresados.'
  }
  if (err?.response?.status === 429) return 'Demasiados intentos. Espera unos minutos.'
  if (!err?.response) return 'No hay conexión con el servidor. Revisa tu internet e intenta de nuevo.'
  return fallback
}
